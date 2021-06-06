AWS CLOUD MINING EXTENSION
==========================

This Skepticoin Extension enables the option to run Skepticoin Mining on the Amazon Web Services (AWS) cloud. The extension consists of a set of Cloud Formation Templates that automate the deployment of miners to a cluster of EC2 Instances managed by an Auto-Scaling Group.

## Why?

Runnning skepticoin miners on AWS is ultimately an asinine idea, because you'll be spending real money payable to a third party, rather than mooching off your existing "free" eletricity supply (assuming someone else is paying for that) and idle hardware.

## No really, WHY??

Despite being an overall terrible idea, there are a couple of reasons you might still feel compelled to Cloud Mine, one of which is selfish, while the other one is good for the Skepticoin Community:

1. You feel the FOMO and you really want to mine some Skeptis, but your existing computers are already busy doing other things such as gaming, or attending Zoom meetings, both of which don't co-exist well with skepticoin mining.

2. Running some nodes on business-grade infrastructure helps the overall stability of the Skepticoin peer-to-peer network. Cloud mining nodes are configured with bi-directional connectivity, which can be a challenge to setup correctly on a home Internet router.

## How to Use

1. Pre-requisites: 
    - An AWS Account.
    - An EC2 Key Pair: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html
    - Cloud Formation templates downloaded to your computer (`network.yaml`, `storage.yaml`, `compute.yaml`). These are found in the same folder where this README is located.
    - skepticoin files: `peers.json`, `chain.cache`, and `wallet.json`. You'll need to run skepticoin on your own computer first to obtain these files.
2. Login to the AWS Console and navigate to the Cloud Formation service.
3. Deploy `network.yaml`
    - Click 'Create Stack' -> 'with new resources' -> 'Upload a template file' and select `network.yaml` from your computer.
    - Click Next to get to the Parameters tab. Update the SSHLocation parameter to whitelist your home/office IP address. 
    - Click Next, Next, then Create Stack.
4. Deploy `storage.yaml` and upload data files
    - Click 'Create Stack' -> 'with new resources' -> 'Upload a template file' and select `storage.yaml` from your computer
    - Click Next to get to the Parameters tab. Pick a unique name for your public skepticoin bucket. This where you will publish `peers.json` and `chain.cache`
    - Click Next, Next, then Create Stack. Click the *Outputs* tab and note down the names of the Public and Private Buckets
    - Navigate to the AWS S3 Service. Go to the Public Bucket and upload `peers.json` and `chain.cache`
    - Go to the Private Bucket and upload your `wallet.json`.
5. Deploy `compute.yaml`
    - Click 'Create Stack' -> 'with new resources' -> 'Upload a template file' and select `compute.yaml` from your computer
    - Review the Parameters.
    - Click Next, Next, then Create Stack.
6. Monitoring status
    -  In the AWS Console, navigate over to Cloud Watch -> Log Groups to view logs from the mining instances.