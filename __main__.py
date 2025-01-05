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
    routes=[{  # Changed to dictionary instead of RouteTableRouteArgs
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
            cidr_blocks=my_ip.apply(lambda ip: [ip])  # Transform secret into list
        ),
        # Rails application
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=3000,
            to_port=3000,
            cidr_blocks=my_ip.apply(lambda ip: [ip])  # Transform secret into list
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
        'volumeSize': 20,  # Increased to 40GB for Guix installation
        'volumeType': 'gp3'
    },
    tags={'Name': 'btc-tracker'},
    user_data='''#!/bin/bash
# Update system packages
dnf update -y

# Install basic tools and dependencies
dnf install -y git wget gnupg2 gpg-agent pinentry

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

# Initialize GPG
mkdir -p /root/.gnupg
chmod 700 /root/.gnupg
echo "allow-loopback-pinentry" > /root/.gnupg/gpg-agent.conf
echo "pinentry-mode loopback" > /root/.gnupg/gpg.conf

# Start gpg-agent
gpg-agent --daemon

# Import required GPG keys
wget "https://sv.gnu.org/people/viewgpg.php?user_id=127547" -O maxim.key
wget "https://sv.gnu.org/people/viewgpg.php?user_id=15145" -O ludo.key
gpg --batch --yes --import maxim.key
gpg --batch --yes --import ludo.key

# Download and run Guix installer
wget https://git.savannah.gnu.org/cgit/guix.git/plain/etc/guix-install.sh
chmod +x guix-install.sh
yes '' | ./guix-install.sh

# Clean up
rm -f maxim.key ludo.key

# Install glibc-locales and set up environment for ec2-user
su - ec2-user -c "guix package -i glibc-locales"

# Configure locale settings for both root and ec2-user
cat >> /root/.bashrc <<EOL
export GUIX_LOCPATH="$HOME/.guix-profile/lib/locale"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
EOL

cat >> /home/ec2-user/.bashrc <<EOL
export GUIX_LOCPATH="$HOME/.guix-profile/lib/locale"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
EOL

# Set proper ownership of ec2-user's .bashrc
chown ec2-user:ec2-user /home/ec2-user/.bashrc

# Source the environment for the current session
export GUIX_LOCPATH="/home/ec2-user/.guix-profile/lib/locale"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

# Install Ruby, Rails, and PostgreSQL as ec2-user
su - ec2-user -c "guix package -i ruby ruby-rails postgresql"

# Initialize PostgreSQL - now with proper environment sourcing
su - ec2-user -c "bash -l -c 'mkdir -p ~/postgres-data && initdb -D ~/postgres-data'"

# Start PostgreSQL with proper environment
su - ec2-user -c "bash -l -c 'postgres -D ~/postgres-data &'"

# Wait for PostgreSQL to start
sleep 5

# Create database user with proper environment
su - ec2-user -c "bash -l -c 'createuser -s ec2-user'"

# Source the new environment variables
source /root/.bashrc

''')

# Export useful information
pulumi.export('instance_id', instance.id)
pulumi.export('public_ip', instance.public_ip)
pulumi.export('public_dns', instance.public_dns)