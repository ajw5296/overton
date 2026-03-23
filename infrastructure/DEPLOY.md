# Deploying Overton Dashboard to AWS ECS Fargate

## Prerequisites

- AWS CLI configured with appropriate credentials
- Docker installed locally
- Your VPC ID and at least 2 public subnet IDs (in different AZs)

## Step 1: Deploy CloudFormation Stack

```bash
aws cloudformation deploy \
  --template-file infrastructure/ecs-fargate.yaml \
  --stack-name overton-dashboard \
  --parameter-overrides \
    VpcId=vpc-b653f0cb \
    SubnetIds=subnet-62ba2743,subnet-c03caba6 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

Your VPC and subnets:
- VPC: `vpc-b653f0cb`
- Subnets: `subnet-62ba2743`, `subnet-c03caba6`, `subnet-caef35fb`, `subnet-c6597f8b`

(Using 2 subnets is sufficient for ALB, but you can use more if needed)

## Step 2: Get ECR Repository URI

```bash
aws cloudformation describe-stacks \
  --stack-name overton-dashboard \
  --query 'Stacks[0].Outputs[?OutputKey==`ECRRepositoryUri`].OutputValue' \
  --output text
```

## Step 3: Build and Push Docker Image

```bash
# Navigate to dashboard directory
cd dashboard

# Authenticate Docker to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build the image
docker build -t overton-dashboard .

# Tag the image
docker tag overton-dashboard:latest <ecr-repo-uri>:latest

# Push to ECR
docker push <ecr-repo-uri>:latest
```

## Step 4: Copy Data Files

The dashboard needs the data files. You have two options:

### Option A: Bake data into the Docker image (simpler)

Before building, copy the data folder into the dashboard directory:

```bash
cp -r data/overton_exports dashboard/data/overton_exports
```

Then rebuild and push the image.

### Option B: Use S3 + EFS (more complex, better for large/changing data)

This requires additional CloudFormation resources. Let me know if you need this approach.

## Step 5: Force New Deployment (after pushing new image)

```bash
aws ecs update-service \
  --cluster overton-dashboard-cluster \
  --service overton-dashboard-service \
  --force-new-deployment \
  --region us-east-1
```

## Step 6: Get Dashboard URL

```bash
aws cloudformation describe-stacks \
  --stack-name overton-dashboard \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
  --output text
```

## Updating the Dashboard

After making code changes:

1. Rebuild the Docker image
2. Push to ECR
3. Force a new deployment (Step 5)

## Monitoring

View logs in CloudWatch:
- Log group: `/ecs/overton-dashboard`

Or via CLI:
```bash
aws logs tail /ecs/overton-dashboard --follow
```

## Cleanup

To delete all resources:

```bash
# First, delete all images from ECR
aws ecr batch-delete-image \
  --repository-name overton-dashboard \
  --image-ids "$(aws ecr list-images --repository-name overton-dashboard --query 'imageIds[*]' --output json)"

# Then delete the stack
aws cloudformation delete-stack --stack-name overton-dashboard
```

## Cost Estimation

With default settings (256 CPU, 512MB memory, 1 task):
- Fargate: ~$10-15/month
- ALB: ~$16-20/month
- ECR: <$1/month
- CloudWatch Logs: <$1/month

**Total: ~$25-35/month**

To reduce costs:
- Use FARGATE_SPOT (less reliable but cheaper)
- Scale to 0 when not in use
