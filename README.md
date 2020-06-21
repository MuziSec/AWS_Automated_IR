AWS Automated IR

This project is aimed at automating as much of the incident response process in AWS as possible. AWS provides a number of services that can be leveraged to automate the entire incident response lifecycle. The goal of this project is to provide utilities that allow for:

    Containment: Tag a resource for automatic containment, including restrictive security groups/policies for EC2/S3 resources, disabling user access (disable access keys), etc.

    Artifact Collection and Analysis: Collect forensic artifacts using tools such as margaritashotgun, snapshots, live response scripts, etc. Collect this data and upload to specified S3 bucket for easy access from IR VPC/Forensic analysis machines.

    Remediation: Remediate compromised EC2 instances, redeploy AMIs, etc.
    
    
 Eventually I think I'll turn this into an AWS Step Function... we'll see. 
