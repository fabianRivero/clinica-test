# AWS Cloud Storage Setup — Owner Runbook

Slice 4 of `cloud-storage-migration`. Audience: project owner (dueño).
Pre-apply blocker for the live S3 cutover (proposal Gate 4).

## Prerequisite

- AWS account with payment method on file. Business support plan is
  optional — basic support covers this rollout.
- 1Password vault access.

## HIPAA note

Before storing clinical data, sign the **AWS BAA** at
<https://aws.amazon.com/compliance/hipaa-eligible-services/>. Until
the BAA is signed, use the bucket only for non-PHI data. Record the
BAA reference in 1Password under `AWS / BAA`.

## Steps

1. **Sign in to AWS Console** as the `admin` IAM user (NOT root).
2. **Sign the BAA** if clinical PHI will land in the bucket. Record
   the reference number in 1Password.
3. **Create the bucket** `proyecto-c-clinical-prod` in region
   `sa-east-1` (S3 → Buckets → Create bucket). Block all public access
   at creation. Repeat for `proyecto-c-clinical-dev` and
   `proyecto-c-clinical-staging`.
4. **Enable all 4 public-access-block flags** (Permissions → Block
   public access): `BlockPublicAcls`, `IgnorePublicAcls`,
   `BlockPublicPolicy`, `RestrictPublicBuckets` — all TRUE.
5. **Enable Versioning** under Properties → Bucket Versioning → Enable
   (proposal Gate 7 — defends clinical PDFs against accidental delete).
6. **Enable Server Access Logs** to a dedicated logs bucket
   `proyecto-c-clinical-prod-logs` in the same region. Use the log
   fields from design §10: `BucketOwner`, `Bucket`, `Time`, `RemoteIP`,
   `Requester`, `RequestID`, `Operation`, `Key`, `RequestURI`,
   `HTTPStatus`, `ErrorCode`, `BytesSent`, `ObjectSize`, `TotalTime`,
   `TurnAroundTime`, `Referer`, `UserAgent`, `VersionId`.
7. **Create the IAM user** `proyecto-c-app-prod` with programmatic
   access only (no console password).
8. **Attach the inline policy** below (paste the JSON exactly,
   substituting the bucket name for `<env>`):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "BucketList",
         "Effect": "Allow",
         "Action": ["s3:ListBucket"],
         "Resource": "arn:aws:s3:::proyecto-c-clinical-<env>",
         "Condition": { "StringEquals": { "aws:RequestedRegion": "sa-east-1" } }
       },
       {
         "Sid": "BucketObjectRW",
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
         "Resource": "arn:aws:s3:::proyecto-c-clinical-<env>/*",
         "Condition": { "StringEquals": { "aws:RequestedRegion": "sa-east-1" } }
       },
       {
         "Sid": "DenyNonSaEast1",
         "Effect": "Deny",
         "Action": "s3:*",
         "Resource": "*",
         "Condition": { "StringNotEquals": { "aws:RequestedRegion": "sa-east-1" } }
       }
     ]
   }
   ```

9. **Store the access key + secret** in 1Password under
   `AWS / proyecto-c-app-prod / prod`. The app reads them from env
   vars `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.
10. **Verify from a developer machine**:

    ```bash
    aws s3 ls s3://proyecto-c-clinical-prod --profile test
    ```

    Expect an empty listing, no errors. `AccessDenied` means a typo in
    the inline policy — re-paste from step 8.

## Ops follow-ups (after live cutover)

- Cron: `0 2 * * * cd /srv/proyecto-c/backend && /srv/proyecto-c/backend/env/bin/python manage.py backfill_media --resume`
  until the `_BACKFILL_COMPLETE` sentinel exists at the bucket root.
- CloudWatch billing alarm at $30/mo on `EstimatedCharges` (proposal
  Gate 7).
- Cron: `0 3 * * * cd /srv/proyecto-c/backend && /srv/proyecto-c/backend/env/bin/python manage.py audit_log_retention --days=90`.
- Rotate the IAM access key every 90 days. Log rotation in 1Password
  under `AWS / proyecto-c-app-prod / rotation-log`.

## Rollback

Flip `STORAGE_PROVIDER=local` in the production env and redeploy.
The signed-URL endpoint returns 503 and the frontend falls back to
local `/media/...` via the `useSignedUrl` helper feature flag
(`frontend/aesthetic-clinic/src/services/media.tsx`).
