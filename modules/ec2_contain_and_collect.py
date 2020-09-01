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
def isolate_ec2(ec2, instance_id):
    # TO DO: Switch VPC Security Group to isolate the instance
    return

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
    
    
def run_command(instance_id, aws_region, commands):

    ssm_client = boto3.client('ssm', region_name=aws_region)

    response = ssm_client.send_command(
        InstanceIds=[
            instance_id
        ],
        DocumentName="AWS-RunShellScript",
        # TimeoutSeconds=1800,
        Parameters={
            'commands':commands
        },
    )
    
    # Get command_id and instance_id to check output
    command_id = response['Command']['CommandId']
    instance_id = response['Command']['InstanceIds'][0]
    
    # Wait for command to complete
    time.sleep(60)
    
    try:
        cmd_response = ssm_client.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id
        )
    except Exception as e:
        print(f'Could not get response: {e}')

        
    return cmd_response
    
def capture_memory(instance_id, aws_region, commands):
    ''' Capture Memory and Upload to S3. Returns S3 bucket key (~filepath)'''
    
    # Execute memdump and return path of memdump output
    response = run_command(instance_id, aws_region, commands)
    memdump_path = response['StandardOutputContent'].rstrip()
    
    # S3 Key
    key = 'memdump ' + instance_id
    
    # Generate presigned_url for upload
    presigned_url = get_s3_presigned('<s3_bucket_name>', key, 'put_object')
    
    # Upload memdump to S3
    try:
        upload_response = upload_files(instance_id, aws_region, presigned_url, memdump_path)
    except Exception as e:
        return False
    
    # Return memdump key in S3 bucket
    return key
    
def build_volatility_profile(instance_id, aws_region, commands):
    ''' Build Volatility Profile and upload to S3. Returns S3 bucket key (~filepath)'''
    
    # Grab requirements and build profile
    response = run_command(instance_id, aws_region, commands)
    
    # Vol profile path
    vol_profile_path = "/home/ec2-user/Linux_`uname -r`.zip"
    
    
    # S3 Key
    key = 'VolatilityProfile ' + instance_id
    
    # Generate presigned_url for upload
    presigned_url = get_s3_presigned('<s3_bucket_name>', key, 'put_object')
    
    # Upload profile to S3
    try:
        upload_response = upload_files(instance_id, aws_region, presigned_url, vol_profile_path)
    except Exception as e:
        return False
    
    # Return profile key in S3 bucket
    return key
   
    
    
def get_s3_presigned(bucket_name, object_name, method, expiration=7200):
    '''Generate a pre-signed URL to allow S3 upload of files'''
    s3 = boto3.client('s3')
    
    try:
        response = s3.generate_presigned_url(method, Params={'Bucket': bucket_name, 'Key': object_name}, ExpiresIn=expiration, HttpMethod='PUT')
    except ClientError as e:
        print(f'There was an error generating the presigned url: {e}')
        return None
    return response

def upload_files(instance_id, aws_region, presigned_url, filepath):
    '''Upload files to S3 bucket'''
    
    # Create the command to execute upload
    cmd_str = f"curl -v --upload-file {filepath} '{presigned_url}'"
    #print(f'Command_String is: {cmd_str}')
    commands = [cmd_str]
    
    # Execute the upload
    response = run_command(instance_id, aws_region, commands)
    
    return response
   
    

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
    print(collect_metadata(ec2, instance_id))
    
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
    
    
    # Capture Memory
    memdump_commands = ['/root/avml /root/memdump.lime','find /root/ -name memdump.lime']
    s3_memdump_key = capture_memory(instance_id, aws_region, memdump_commands)
    print(f'S3 Memdump Key: {s3_memdump_key}')
    
    
    # Build Volatility Profile
    build_vol_profile_commands = ['sudo su ec2-user', 'sudo yum install -y kernel-devel-$(uname -r)', 'sudo yum install -y libdwarf-tools', 'git clone https://github.com/volatilityfoundation/volatility.git /home/ec2-user/volatility', 'sudo chown -R ec2-user /home/ec2-user/volatility/tools/linux', 'cd /home/ec2-user/volatility/tools/linux/', 'zip /home/ec2-user/Linux_`uname -r`.zip tools/linux/module.dwarf /boot/System.map-`uname -r`', 'find /home/ec2-user/ -name Linux_`uname -r`.zip']
    s3_vol_profile_key = build_volatility_profile(instance_id, aws_region, build_vol_profile_commands)
    print(f'S3 Vol Profile Key: {s3_vol_profile_key}')
    

    

