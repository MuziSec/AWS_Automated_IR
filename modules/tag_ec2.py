import requests
import argparse
import boto3
import logging
import pprint


def tag_ec2(client, instance_id, tag, tag_desc):
    # Try to create tag on EC2 instance with provided tag and desc.
    try:
        response = client.create_tags(
            Resources=[
                instance_id
            ],
            Tags=[
                {
                    'Key': tag,
                    'Value': tag_desc
                }
            ]
        )
    except Exception as e:
        print(f'The following exception has occurred: {e}')
        return False

    # Check response code for successful tag
    status = response['ResponseMetadata']['HTTPStatusCode']
    if status == 200:
        return True
    return

def delete_tag_ec2(client, instance_id, tag):
    # Try to delete tag on EC2 instance with provided tag.
    try:
        response = client.delete_tags(
            Resources=[
                instance_id
            ],
            Tags=[
                {
                    'Key': tag
                }
            ]
        )
    except Exception as e:
        print(f'The following exception has occured: {e}')

    # Check response code for successful tag removal
    status = response['ResponseMetadata']['HTTPStatusCode']
    if status == 200:
        return True
    return
    

def main():

    # Parse user provided arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=False, type=str, help="Provide EC2 InstanceId to be tagged.")
    parser.add_argument("--tagdesc", required=False, type=str, help="Optional tag description.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--describe", action='store_true', help="Describe all EC2 instances.")
    group.add_argument("--tag", nargs='?', const="IR_Contained", type=str, help="Tag EC2 instance with IR_Contained tag. Default=IR_Contained")
    group.add_argument("--untag", nargs='?', const="IR_Contained", type=str,  help="Remove IR_Contained tag from EC2 instance. Default=IR_Contained")
    args = parser.parse_args()

    # init boto3 client
    client = boto3.client('ec2')

    # init pp
    pp = pprint.PrettyPrinter()

    # Check for optional args
    if args.tagdesc:
        tag_desc = args.tagdesc
    else:
        tag_desc = "This EC2 instance has been contained by the security incident response team. Please reach out to the security team for additional information."

    # Describe EC2 Instances
    if args.describe:
        instances = client.describe_instances()
        for r in instances['Reservations']:
            for i in r['Instances']:
                pp.pprint(i)
                
    # Tag EC2 Instance
    if args.tag:
        # If EC2 ID not provided, exit
        if not args.id:
            print("EC2 InstanceId required to tag. Please retry and provide the required InstanceId")
            return
        # Make tag request
        else:
            response = tag_ec2(client, args.id, args.tag, tag_desc)
            if response:
                print(f'Successfully tagged EC2 instance {args.id} with tag Key: {args.tag}, Value: {tag_desc}.')
            else:
                print(f'Tagging for EC2 instance {args.id} was unsuccessful.')

    # Untag EC2 Instance
    if args.untag:
        # If EC2 ID not provided, exit
        if not args.id:
            print("EC2 InstanceId required to tag. Please retry and provide the required InstanceId.")
            return
        # Make delete tag request
        else:
            response = delete_tag_ec2(client, args.id, args.untag)
        if response:
            print(f'Successfully untagged {args.untag} tag EC2 instance {args.id}.')
        else:
            print(f'Untagging EC2 instance {args.id} was unsuccessful.')

if __name__ == "__main__":
    main()
