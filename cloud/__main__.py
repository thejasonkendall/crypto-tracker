import pulumi
from pulumi_aws import ec2, get_availability_zones

# Get the AWS region from Pulumi config
config = pulumi.Config()
region = config.get('region') or 'us-east-1'
vpc_cidr = config.require('vpc_cidr')  # Not a secret
subnet_cidr = config.require('subnet_cidr')  # Not a secret
my_ip = config.require_secret('my_ip')  # This is a secret

# Create a new VPC
vpc = ec2.Vpc(
    'btc-tracker-vpc',
    cidr_block=vpc_cidr,
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={'Name': 'btc-tracker-vpc'}
)

# Create an Internet Gateway
igw = ec2.InternetGateway(
    'btc-tracker-igw',
    vpc_id=vpc.id,
    tags={'Name': 'btc-tracker-igw'}
)

# Create a public subnet
public_subnet = ec2.Subnet(
    'btc-tracker-subnet',
    vpc_id=vpc.id,
    cidr_block=subnet_cidr,
    availability_zone=get_availability_zones().names[0],
    map_public_ip_on_launch=True,
    tags={'Name': 'btc-tracker-subnet'}
)

# Create a route table
route_table = ec2.RouteTable(
    'btc-tracker-rt',
    vpc_id=vpc.id,
    routes=[{
        'cidr_block': '0.0.0.0/0',
        'gateway_id': igw.id
    }],
    tags={'Name': 'btc-tracker-rt'}
)

# Associate the route table with the subnet
route_table_association = ec2.RouteTableAssociation(
    'btc-tracker-rt-assoc',
    subnet_id=public_subnet.id,
    route_table_id=route_table.id
)

security_group = ec2.SecurityGroup(
    'btc-tracker-sg',
    description='Security group for BTC tracker instance',
    vpc_id=vpc.id,
    ingress=[
        # SSH access
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=22,
            to_port=22,
            cidr_blocks=my_ip.apply(lambda ip: [ip])
        ),
        # Rails application
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=3000,
            to_port=3000,
            cidr_blocks=my_ip.apply(lambda ip: [ip])
        )
    ],
    egress=[
        # Allow all outbound traffic
        ec2.SecurityGroupEgressArgs(
            protocol='-1',
            from_port=0,
            to_port=0,
            cidr_blocks=['0.0.0.0/0']
        )
    ],
    tags={'Name': 'btc-tracker-sg'}
)

# Get the latest Amazon Linux 2023 AMI
ami = ec2.get_ami(
    most_recent=True,
    owners=['amazon'],
    filters=[
        {
            'name': 'name',
            'values': ['al2023-ami-2023.*-x86_64']
        }
    ]
)

# Create an EC2 key pair
key_pair = ec2.KeyPair(
    'btc-tracker-key',
    public_key=config.require('public_key'),
    tags={'Name': 'btc-tracker-key'}
)

# Create the EC2 instance
instance = ec2.Instance(
    'btc-tracker-instance',
    instance_type='t3.micro',
    ami=ami.id,
    subnet_id=public_subnet.id,
    vpc_security_group_ids=[security_group.id],
    key_name=key_pair.key_name,
    root_block_device={
        'volumeSize': 20,
        'volumeType': 'gp3'
    },
    tags={'Name': 'btc-tracker'},
    user_data='''#!/bin/bash

echo "########## LOOK Update system packages"
dnf update -y

echo "########## Install basic tools and dependencies"
dnf install -y git wget dnf-utils

echo "################# LOOK, DONE WITH INSTALL STEPS"

echo "########## Install Ruby"
dnf install -y ruby3.2

echo "[INIT] Installing PostgreSQL 16"
dnf install -y postgresql16 postgresql16-server

echo "[INIT] Initializing PostgreSQL database"
postgresql-setup initdb

echo "[INIT] Starting and enabling PostgreSQL service"
systemctl enable postgresql
systemctl start postgresql

echo "[INIT] Configuring PostgreSQL local connections"
cp /var/lib/pgsql/data/pg_hba.conf /var/lib/pgsql/data/pg_hba.conf.bak
sed -i 's/ident/trust/g' /var/lib/pgsql/data/pg_hba.conf
sed -i 's/peer/trust/g' /var/lib/pgsql/data/pg_hba.conf
systemctl restart postgresql

echo "[INIT] Creating PostgreSQL user"
su - postgres -c "createuser -s ec2-user"

echo "[INIT] Installing Rails dependencies"
dnf install -y ruby3.2-devel make gcc gcc-c++ redhat-rpm-config libyaml-devel

echo "[INIT] Installing Rails"
gem install rails

echo "[INIT] Setting up environment"
echo 'export PATH="$PATH:$HOME/.local/bin:/usr/local/bin"' >> /home/ec2-user/.bashrc
chown ec2-user:ec2-user /home/ec2-user/.bashrc

echo "[INIT] Installation Complete"
''')

# Add this to the script above later..
# sudo dnf install -y postgresql-devel
# bundle install
# rails db:create db:migrate RAILS_ENV=production
# rails assets:precompile RAILS_ENV=production
# rails secret
# export SECRET_KEY_BASE to output of `rails secret`
# rails server -e production -p 3000 -b 0.0.0.0

# Export useful information
pulumi.export('instance_id', instance.id)
pulumi.export('public_ip', instance.public_ip)
pulumi.export('public_dns', instance.public_dns)