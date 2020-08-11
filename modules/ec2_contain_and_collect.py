import boto3
import json
import os
import time

from base64 import b64decode
import urllib3

def collect_metadata(ec2, instance_id):
    # Collect metadata
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id],)
        return response
    except Exception as e:
        return(f'Could not collect instance metadata. The following error occurred: {e}')

def enable_termination_protection(ec2, instance_id):

    # Check to see if already enabled
    try:
        check_term_protection = ec2.describe_instance_attribute(InstanceId=instance_id, Attribute='disableApiTermination')
    except Exception as e:
        return(f"Could not describe instance attribute. The following exception has occurred: {e}")
    
    # Get protection value from response
    protection_value = check_term_protection['DisableApiTermination']['Value']
    # print(protection_value)
    
    # If termination protection is already on return True
    if protection_value == True:
        # print("Termination protection is already on.")
        return True
    # If termination protection is not already on, try to turn it on
    else:
        try:
            enable = ec2.modify_instance_attribute(InstanceId=instance_id, Attribute='disableApiTermination', Value='True')
        except Exception as e:
            return(f"Termination protection couldn't be enabled. The following exception has occured: {e}")
            
    # Check new value to ensure success
    protection_value = enable['DisableApiTermination']['Value']
    if protection_value == True:
        # print("Termination protection enabled")
        return True
    else:
        return False

def get_volumes(ec2, instance_id):
    # Get all volumes in use for region
    try:
        volumes = ec2.describe_volumes( Filters=[{'Name': 'status', 'Values': ['in-use']}])
    except Exception as e:
        return(f"Could not describe volumes. The following exception has occured: {e}")
        
    # Loop through volumes and identify any volumes in use by EC2 of interest and store in ir_volumes
    ir_volumes = []
    for volume in volumes['Volumes']:
        if volume['Attachments'][0]['InstanceId'] == instance_id:
            ir_volumes.append(volume)
    return ir_volumes

def isolate_ec2(ec2, instance_id):
    # TO DO: Switch VPC Security Group to isolate the instance
    return

def detach_autoscaling(instance_id):
    # Get autoscaling group names for instance
    autoscaling = boto3.client('autoscaling')
    try:
        asg_response = autoscaling.describe_auto_scaling_instances(InstanceIds=[instance_id],)
    except Exception as e:
        return(f'There was an issue describing the instance: {e}')
    # Store all asgs for the instance in asg dict
    asg_dict = {}    
    # Remove from asg
    for asi in asg_response['AutoScalingInstances']:
        asg = asi['AutoScalingGroupName']
        try:
            response = autoscaling.detach_instances(InstanceIds=[instance_id], AutoScalingGroupName=asg, ShouldDecrementDesiredCapacity=True)
        except Exception as e:
            return(f'There was an issue detaching {instance_id} from {asg}: {e}')
        
        # Check if successfully detached
        if 'Detaching' in response['Activities'][0]['Description']:
            asg_dict[asg] = response['Activities'][0]['Description']
        else:
            asg_dict[asg] = "Failed to detach from auto scaling group."
    return asg_dict

def deregister_elb_service(instance_id):
    # Get ELB Names
    elb = boto3.client('elb')
    try:
        elb_response = elb.describe_load_balancers()
    except Exception as e:
        return(f'There was an issue describing the load balancers: {e}')
    # Store all elbs for the instance in elb dict
    elb_dict = {}
    # Remove from ELB
    for load_balancer in elb_response['LoadBalancerDescriptions']:
        load_balancer_name = load_balancer['LoadBalancerName']
        try:
            deregister_response = elb.deregister_instances_from_load_balancer(
                LoadBalancerName=load_balancer_name, 
                Instances=[
                    {
                        'InstanceId': instance_id
                    },
                ]
            )
        except Exception as e:
            return(f'There was an issue deregistering {instance_id} from ELB: {load_balancer_name}: {e}')
        # Check if instance successfully deregistered from ELB
        if instance_id not in [instance['InstanceId'] for instance in deregister_response['Instances']]:
            elb_dict[load_balancer_name] = f'{instance_id} successfully deregistered from {load_balancer_name}'
        else:
            elb_dict[load_balancer_name] = f'{instance_id} failed to deregister from {load_balancer_name}'
    return elb_dict

def snapshot_ec2(ec2, instance_id):
    # Loop through volumes of interest and snapshot them
    ir_volumes = get_volumes(ec2, instance_id)
    response_dict = {}
    for volume in ir_volumes:
        print(volume['Attachments'][0]['VolumeId'])
        volume_id = volume['Attachments'][0]['VolumeId']
        try:
            result = ec2.create_snapshot(VolumeId=volume_id,Description='Created by security team IR lambda function.')
        except Exception as e:
            print(f'There was an exception creating the snapshot: {e}')
                    # print(f'Result of create snapshot: {result}')
        if "snap" in result['SnapshotId']:
            response_dict[volume_id] = result['SnapshotId']
        else:
            response_dict[volume_id] = "failed"
        
    return response_dict
    
def capture_memory(instance_id, aws_region):

    ssm_client = boto3.client('ssm', region_name=aws_region)

    response = ssm_client.send_command(
        InstanceIds=[
            instance_id
        ],
        DocumentName="AWS-RunShellScript",
        # TimeoutSeconds=1800,
        Parameters={
            'commands':[
                '/root/avml /root/memdump.lime'
            ]
        },
    )
    
    command_id = response['Command']['CommandId']
    instance_id = response['Command']['InstanceIds'][0]
    time.sleep(2)
    response = ssm_client.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
    output = response['StandardOutputContent']
    print(f'Response output is: {output}')

def build_volatility_profile(instance_id, aws_region):
    # Add profile to volatility/volatility/plugins/overlays/linux/ and then add x64 or x32 to name of zip (and exclude .zip)
    ssm_client = boto3.client('ssm', region_name=aws_region)
    
    cmd0 = f'sudo su ec2-user'
    cmd1 = f'sudo yum install -y kernel-devel-$(uname -r)'
    cmd2 = f'sudo yum install -y libdwarf-tools'
    cmd3 = f'git clone https://github.com/volatilityfoundation/volatility.git /home/ec2-user/volatility'
    cmd4 = f'sudo chown -R ec2-user /home/ec2-user/volatility/tools/linux'
    cmd5 = f'cd /home/ec2-user/volatility/tools/linux/'
    cmd6 = f'make'
    cmd7 = f'cd /home/ec2-user/volatility'
    cmd8 = f'zip /home/ec2-user/Linux_`uname -r`.zip tools/linux/module.dwarf /boot/System.map-`uname -r`'
    cmd9 = f'cp /home/ec2-user/Linux_`uname -r`.zip volatility/plugins/overlays/linux/'
    cmd10 = f'ls /home/ec2-user/*.zip'

    response = ssm_client.send_command(
        InstanceIds=[
            instance_id
        ],
        DocumentName="AWS-RunShellScript",
        # TimeoutSeconds=1800,
        Parameters={
            'commands':[
                cmd1,
                cmd2,
                cmd3,
                cmd4,
                cmd5,
                cmd6,
                cmd7,
                cmd8,
                cmd9,
                cmd10

            ]
        },
    )
    
    cmdId = response.get("Command").get("CommandId")

    time.sleep(30)
    
    cmd_response = ssm_client.get_command_invocation(
        CommandId=cmdId,
        InstanceId=instance_id
    )
    print(f'Command Response: {cmd_response}')
    
def get_s3_presigned(bucket_name, object_name, expiration=7200):
    '''Generate a pre-signed URL to allow S3 upload of files'''
    s3 = boto3.client('s3')
    
    try:
        response = s3.generate_presigned_url('get_object', Params={'Bucket': bucket_name, 'Key': object_name}, ExpiresIn=expiration, HttpMethod='PUT')
    except ClientError as e:
        print(f'There was an error generating the presigned url: {e}')
        return None
    return response

def get_files(instance_id, aws_region):
    '''Get pre-signed URL upload memdump and volatility profile'''
    memdump_url = get_s3_presigned('s3_bucket', 'memdump')
    print(f'Memdump URL: {memdump_url}')
    
    # open ssm client
    ssm_client = boto3.client('ssm', region_name=aws_region)
    
    cmd0 = f'curl -v --upload-file /home/ec2-user/memdump.lime {memdump_url}'
    
    response = ssm_client.send_command(
        InstanceIds=[
            instance_id
        ],
        DocumentName="AWS-RunShellScript",
        # TimeoutSeconds=1800,
        Parameters={
            'commands':[
                cmd0

            ]
        },
    )
    
    cmdId = response.get("Command").get("CommandId")
    
    time.sleep(30)
    
    cmd_response = ssm_client.get_command_invocation(
        CommandId=cmdId,
        InstanceId=instance_id
    )
    print(f'Command Response: {cmd_response}')

def lambda_handler(event, context):
    
    detail = event['detail']
    # print(f'This is the event: {event}')
    # print(f'Event detail: {detail}')
    
    # If this event is not about an ec2 instance, exit
    if not detail['service'] == 'ec2' and detail['resource-type'] == 'instance':
        return
    
    # Get AWS Region for Event so lambda can handle any region
    aws_region = event['region']
    # print(f'Region: {aws_region}')
    
    # init boto3 client
    # In future, this should be updated to work with all regions
    ec2 = boto3.client('ec2', region_name=aws_region)

        
    # Grab EC2 instance_id from Event
    instance_id = event['resources'][0].split("/")[1]
    # print(f'Instance: {instance_id}')
    
    
    # Get EC2 instance metadata
    # print(collect_metadata(ec2, instance_id))
    '''
    # Prevent EC2 termination 
    
    term_protection = enable_termination_protection(ec2, instance_id)
    if term_protection == True:
        print("Termination Protection enabled successfully.")
    elif term_protection == False:
        print("Termination Protection couldn't be turned on.")
    else:
        print(term_protection)
    
    
    # Snapshot EC2
    print(f'Here are the corresponding snapshots: (snapshot_ec2(ec2, instance_id))')
    
    
    # Detach EC2 from autoscaling
    print(detach_autoscaling(instance_id))
    
    
    #Deregister Load Balancers
    print(deregister_elb_service(instance_id))
    '''
    
    # Capture Memory
    #capture_memory(instance_id, aws_region)
    
    # Build Volatility Profile
    # build_volatility_profile(instance_id, aws_region)
    
    # Upload Files to S3
    get_files(instance_id, aws_region)

