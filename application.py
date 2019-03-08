from troposphere import (
    AWS_ACCOUNT_ID,
    AWS_REGION,
    Equals,
    GetAtt,
    iam,
    Join,
    logs,
    Not,
    Output,
    Parameter,
    Ref,
)

from troposphere.ecs import (
    ContainerDefinition,
    DeploymentConfiguration,
    Environment,
    LoadBalancer,
    LogConfiguration,
    PortMapping,
    Service,
    TaskDefinition,
)

from cluster import (
    autoscaling_group_name,
    application_listener,
    cluster,
    application_target_group,
    web_worker_port,
)

from template import template

application_revision = Ref(template.add_parameter(Parameter(
    "WebAppRevision",
    Description="An optional docker app revision to deploy",
    Type="String",
    Default="",
)))


web_worker_cpu = Ref(template.add_parameter(Parameter(
    "WebWorkerCPU",
    Description="Web worker CPU units",
    Type="Number",
    Default="256",
)))


web_worker_memory = Ref(template.add_parameter(Parameter(
    "WebWorkerMemory",
    Description="Web worker memory",
    Type="Number",
    Default="500",
)))


web_worker_desired_count = Ref(template.add_parameter(Parameter(
    "WebWorkerDesiredCount",
    Description="Web worker task instance count",
    Type="Number",
    Default="1",
)))


web_log_group = logs.LogGroup(
    "WebLogs",
    template=template,
    RetentionInDays=365,
    DeletionPolicy="Retain",
)


template.add_output(Output(
    "WebLogsGroup",
    Description="Web application log group",
    Value=GetAtt(web_log_group, "Arn")
))

log_configuration = LogConfiguration(
    LogDriver="awslogs",
    Options={
        'awslogs-group': Ref(web_log_group),
        'awslogs-region': Ref(AWS_REGION),
    }
)


# ECS task
web_task_definition = TaskDefinition(
    "WebTask",
    template=template,
    # Condition=deploy_condition,
    ContainerDefinitions=[
        ContainerDefinition(
            Name="WebWorker",
            #  1024 is full CPU
            Cpu=web_worker_cpu,
            Memory=web_worker_memory,
            Essential=True,
            Image="registry.hub.docker.com/library/tomcat",
            PortMappings=[PortMapping(
                HostPort=0,
                ContainerPort=web_worker_port,
            )],
            LogConfiguration=LogConfiguration(
                LogDriver="awslogs",
                Options={
                    'awslogs-group': Ref(web_log_group),
                    'awslogs-region': Ref(AWS_REGION),
                }
            ),
            Environment=[
                Environment(
                    Name="PORT",
                    Value=web_worker_port,
                ),
            ],
        )
    ],
)


application_service_role = iam.Role(
    "ApplicationServiceRole",
    template=template,
    AssumeRolePolicyDocument=dict(Statement=[dict(
        Effect="Allow",
        Principal=dict(Service=["ecs.amazonaws.com"]),
        Action=["sts:AssumeRole"],
    )]),
    Path="/",
    Policies=[
        iam.Policy(
            PolicyName="WebServicePolicy",
            PolicyDocument=dict(
                Statement=[dict(
                    Effect="Allow",
                    Action=[
                        "elasticloadbalancing:Describe*",
                        "elasticloadbalancing:RegisterTargets",
                        "elasticloadbalancing:DeregisterTargets",
                        "elasticloadbalancing"
                        ":DeregisterInstancesFromLoadBalancer",
                        "elasticloadbalancing"
                        ":RegisterInstancesWithLoadBalancer",
                        "ec2:Describe*",
                        "ec2:AuthorizeSecurityGroupIngress",
                    ],
                    Resource="*",
                )],
            ),
        ),
    ]
)


application_service = Service(
    "ApplicationService",
    template=template,
    Cluster=Ref(cluster),
    # Condition=deploy_condition,
    DependsOn=[autoscaling_group_name, application_listener.title],
    DeploymentConfiguration=DeploymentConfiguration(
        MaximumPercent=135,
        MinimumHealthyPercent=30,
    ),
    DesiredCount=web_worker_desired_count,
    LoadBalancers=[LoadBalancer(
        ContainerName="WebWorker",
        ContainerPort=web_worker_port,
        TargetGroupArn=Ref(application_target_group),
    )],
    TaskDefinition=Ref(web_task_definition),
    Role=Ref(application_service_role),
)

fh = open("cf_template.yml", "w")
fh.writelines(template.to_yaml())
fh.close()
