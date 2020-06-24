import boto3
import json
import os

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

def isolate_ec2(ec2):
    # TO DO: Switch VPC Security Group to isolate the instance
    return

def detach_autoscaling(ec2, instance_id):
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
        
        # Check if successfully detached and return results
        if 'Detaching' in response['Activities'][0]['Description']:
            asg_dict[asg] = response['Activities'][0]['Description']
        else:
            asg_dict[asg] = "Failed to detach from auto scaling group."
    return asg_dict

def deregister_elb_service(ec2):
    # TO DO: Deregister the EC2 instance from any ELB service
    return

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


def lambda_handler(event, context):
    
    detail = event['detail']
    # print(f'This is the event: {event}')
    # print(f'Event detail: {detail}')
    
    # If this event is not about an ec2 instance, exit
    if not detail['service'] == 'ec2' and detail['resource-type'] == 'instance':
        return
    
    # init boto3 client
    ec2 = boto3.client('ec2', region_name='us-east-1')

    '''
    Check to ensure the tag in this event has been added and the tag remains on the host.
    This ensures that when the tag is removed, this lambda isn't run again. This will serve as main
    handler for lambda.
    '''
    if 'IR_Contained' in detail['changed-tag-keys'] and 'IR_Contained' in detail['tags']:
        # print('IR_Contained is in changed tag keys and current tags.')
        
        # Grab EC2 instance_id from Event
        instance_id = event['resources'][0].split("/")[1]
        
        
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
        
        print(detach_autoscaling(ec2, instance_id))
        
