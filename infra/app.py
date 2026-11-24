import aws_cdk as cdk
from aws_cdk import (
    Duration, RemovalPolicy, Stack, TimeZone,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as patterns,
    aws_iam as iam,
    aws_logs as logs,
    aws_rds as rds,
    aws_scheduler as scheduler,
    aws_scheduler_targets as targets,
    aws_ssm as ssm,
)


class MorningBriefStack(Stack):
    def __init__(self, scope, id, **kwargs):
        super().__init__(scope, id, **kwargs)

        my_ip = self.node.try_get_context("my_ip")
        email = self.node.try_get_context("email")

        # Network: public subnets for the app, private subnets for the database (no NAT = cheaper)
        vpc = ec2.Vpc(self, "Vpc", max_azs=2, nat_gateways=0, subnet_configuration=[
            ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
            ec2.SubnetConfiguration(name="db", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24),
        ])

        # RDS for PostgreSQL (pgvector is built in)
        db = rds.DatabaseInstance(
            self, "Database",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_17_9),
            instance_type=ec2.InstanceType("t4g.micro"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            database_name="morningbrief",
            credentials=rds.Credentials.from_generated_secret("postgres"),
            allocated_storage=20,
            backup_retention=Duration.days(0),
            delete_automated_backups=True,
            deletion_protection=False,
            storage_encrypted=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Docker image: built from the project folder and pushed to ECR by CDK
        image = ecs.ContainerImage.from_asset("..", exclude=["infra", ".git", ".github", "article*.txt", "*.md"])

        def secret(name):
            return ecs.Secret.from_ssm_parameter(
                ssm.StringParameter.from_secure_string_parameter_attributes(
                    self, name, parameter_name=f"/morning-brief/{name}"))

        environment = {
            "DATABASE": f"host={db.db_instance_endpoint_address} dbname=morningbrief user=postgres sslmode=require",
            "LANGFUSE_BASE_URL": "https://cloud.langfuse.com",
            "LANGFUSE_HOST": "https://cloud.langfuse.com",
        }
        secrets = {
            "PGPASSWORD": ecs.Secret.from_secrets_manager(db.secret, "password"),
            "OPENAI_API_KEY": secret("openai-api-key"),
            "LANGFUSE_PUBLIC_KEY": secret("langfuse-public-key"),
            "LANGFUSE_SECRET_KEY": secret("langfuse-secret-key"),
        }

        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)
        arm = ecs.RuntimePlatform(cpu_architecture=ecs.CpuArchitecture.ARM64,
                                  operating_system_family=ecs.OperatingSystemFamily.LINUX)

        # The API on ECS Fargate, behind a load balancer that only your IP can reach
        api = patterns.ApplicationLoadBalancedFargateService(
            self, "Api",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            assign_public_ip=True,
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            runtime_platform=arm,
            open_listener=False,
            task_image_options=patterns.ApplicationLoadBalancedTaskImageOptions(
                image=image,
                container_port=8000,
                environment=environment,
                secrets=secrets,
                log_driver=ecs.LogDrivers.aws_logs(stream_prefix="api", log_retention=logs.RetentionDays.ONE_WEEK),
            ),
        )
        api.target_group.configure_health_check(path="/docs")
        api.load_balancer.connections.allow_from(ec2.Peer.ipv4(my_ip), ec2.Port.tcp(80))
        db.connections.allow_default_port_from(api.service)

        # The daily email task: same image, runs daily_brief.py once a day
        daily = ecs.FargateTaskDefinition(self, "DailyBrief", cpu=256, memory_limit_mib=512, runtime_platform=arm)
        daily.add_container(
            "daily",
            image=image,
            command=["python", "daily_brief.py"],
            environment={**environment, "EMAIL_FROM": email, "EMAIL_TO": email},
            secrets=secrets,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="daily", log_retention=logs.RetentionDays.ONE_WEEK),
        )
        daily.task_role.add_to_policy(iam.PolicyStatement(actions=["ses:SendEmail"], resources=["*"]))
        daily_sg = ec2.SecurityGroup(self, "DailySg", vpc=vpc)
        db.connections.allow_default_port_from(daily_sg)

        # EventBridge Scheduler: every day at 7:00 AM Pakistan time
        scheduler.Schedule(
            self, "DailySchedule",
            schedule=scheduler.ScheduleExpression.cron(minute="0", hour="7", time_zone=TimeZone.ASIA_KARACHI),
            target=targets.EcsRunFargateTask(
                cluster, task_definition=daily, assign_public_ip=True, security_groups=[daily_sg],
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)),
        )

        cdk.CfnOutput(self, "ApiUrl", value=f"http://{api.load_balancer.load_balancer_dns_name}/docs")
        cdk.CfnOutput(self, "RunDailyNow", value=(
            f"aws ecs run-task --cluster {cluster.cluster_name} --task-definition {daily.task_definition_arn} "
            f"--launch-type FARGATE --network-configuration 'awsvpcConfiguration={{subnets=["
            f"{vpc.public_subnets[0].subnet_id}],securityGroups=[{daily_sg.security_group_id}],assignPublicIp=ENABLED}}'"))


app = cdk.App()
MorningBriefStack(app, "MorningBrief")
app.synth()
