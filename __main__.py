import pulumi
from pulumi_aws import ec2, get_availability_zones

# Get the AWS region from Pulumi config
config = pulumi.Config()
region = config.get('region') or 'us-east-1'

# Create a new VPC
vpc = ec2.Vpc(
    'btc-tracker-vpc',
    cidr_block='10.0.0.0/16',
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
    cidr_block='10.0.1.0/24',
    availability_zone=get_availability_zones().names[0],
    map_public_ip_on_launch=True,
    tags={'Name': 'btc-tracker-subnet'}
)

# Create a route table
route_table = ec2.RouteTable(
    'btc-tracker-rt',
    vpc_id=vpc.id,
    routes=[
        ec2.RouteTableRouteArgs(
            cidr_block='0.0.0.0/0',
            gateway_id=igw.id
        )
    ],
    tags={'Name': 'btc-tracker-rt'}
)

# Associate the route table with the subnet
route_table_association = ec2.RouteTableAssociation(
    'btc-tracker-rt-assoc',
    subnet_id=public_subnet.id,
    route_table_id=route_table.id
)

# Create a security group
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
            cidr_blocks=['173.187.119.75/32']  # Consider restricting to your IP
        ),
        # Rails application
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=3000,
            to_port=3000,
            cidr_blocks=['173.187.119.75/32']
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

# Create an EC2 key pair (make sure to save the private key)
key_pair = ec2.KeyPair(
    'btc-tracker-key',
    public_key=config.require('public_key'),  # Add your public key to Pulumi config
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
        'volumeSize': 20,  # 8GB is sufficient for your needs
        'volumeType': 'gp3'
    },
    tags={'Name': 'btc-tracker'},
    user_data='''#!/bin/bash
# Update system packages
dnf update -y

# Install basic tools
dnf install -y git wget

# Install required dependencies for Guix
dnf install -y which locales openssl ca-certificates

# Create the guix user and group
groupadd --system guixbuild
for i in `seq -w 1 10`; do
    useradd -g guixbuild -G guixbuild           \
            -d /var/empty -s `which nologin`     \
            -c "Guix build user $i" --system     \
            "guixbuilder$i";
done

# Download and install Guix binary directly
cd /tmp
wget https://ftp.gnu.org/gnu/guix/guix-binary-1.4.0.x86_64-linux.tar.xz
wget https://ftp.gnu.org/gnu/guix/guix-binary-1.4.0.x86_64-linux.tar.xz.sig

# Extract and install
tar xf guix-binary-1.4.0.x86_64-linux.tar.xz
cd guix-binary-1.4.0.x86_64-linux
./guix-binary-1.4.0.x86_64-linux.sh --system

# Add Guix to system-wide PATH
echo 'GUIX_PROFILE="/root/.config/guix/current"' >> /etc/profile.d/guix.sh
echo '. "$GUIX_PROFILE/etc/profile"' >> /etc/profile.d/guix.sh

# Initialize Guix
source /etc/profile.d/guix.sh
guix pull

# Clean up
cd /tmp
rm -rf guix-binary-1.4.0.x86_64-linux*
''')

# Export useful information
pulumi.export('instance_id', instance.id)
pulumi.export('public_ip', instance.public_ip)
pulumi.export('public_dns', instance.public_dns)