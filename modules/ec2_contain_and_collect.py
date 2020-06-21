import boto3
import json
import os

from base64 import b64decode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

def lambda_handler(event, context):
    
    detail = event['detail']
    print(f'This is the event: {event}')
    print(f'Event detail: {detail}')
    
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
        print('IR_Contained is in changed tag keys and current tags.')
        
        # Grab EC2 instance_id from Event
        instance_id = event['resources'][0].split("/")[1]
        print(instance_id)
        
        # Get all volumes in use for region
        volumes = ec2.describe_volumes( Filters=[{'Name': 'status', 'Values': ['in-use']}])
        # List to store EBS volumes in use by EC2 instance
        ir_volumes = []
        # Loop through volumes and identify any volumes in use by EC2 of interest
        for volume in volumes['Volumes']:
            if volume['Attachments'][0]['InstanceId'] == instance_id:
                ir_volumes.append(volume)
                
                
        # Loop through volumes of interest and snapshot them
        for volume in ir_volumes:
            print(volume['Attachments'][0]['VolumeId'])
            volume_id = volume['Attachments'][0]['VolumeId']
            result = ec2.create_snapshot(VolumeId=volume_id,Description='Created by security team IR lambda function.')
            print(result)
        
    
    


    


