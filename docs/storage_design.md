# DOCUMENT 6: STORAGE DESIGN

This document describes the storage architecture for the platform. We utilize Cloudflare R2 (with MinIO as our local development equivalent) for S3-compatible, zero-egress object storage.

---

## 6.1 Bucket Architecture

### 1. `raw-repositories`
*   **BUCKET**: `raw-repositories`
*   **PURPOSE**: Holds temporary tarball archives of user repository source trees pulled during the ingestion phase.
*   **CONTENTS**: `.tar.gz` zipped files representing the repository branch snapshot.
*   **NAMING**: `repos/{user_id}/{repository_id}/source.tar.gz`
*   **RETENTION**: Deleted **immediately** after the `extract_code_facts` LangGraph node completes. If a job fails, files are removed by the hourly `cleanup_old_jobs` task.
*   **ACCESS**: private (never accessible publicly).
*   **PRESIGNED**: Not applicable (read/written only by backend workers using direct S3 client permissions).

---

### 2. `analysis-artifacts`
*   **BUCKET**: `analysis-artifacts`
*   **PURPOSE**: Stores structured intermediate outputs, such as the full validated facts array and file tree JSON indexes, to keep database row sizes manageable.
*   **CONTENTS**: Structured `.json` data files.
*   **NAMING**: `analysis/{user_id}/{job_id}/facts.json` and `analysis/{user_id}/{job_id}/file_tree.json`
*   **RETENTION**: Retained for 30 days. Deleted automatically when the parent repository is removed or via the daily `cleanup_old_jobs` cleanup task.
*   **ACCESS**: private.
*   **PRESIGNED**: Not applicable (accessed only by backend workers during the document generation steps).

---

### 3. `generated-outputs`
*   **BUCKET**: `generated-outputs`
*   **PURPOSE**: Stores the finalized copies of generated resumes, LinkedIn summaries, readmes, and portfolio pages.
*   **CONTENTS**: `.md` (Markdown), `.txt` files, and compiled `.pdf` documents.
*   **NAMING**: `outputs/{user_id}/{job_id}/{output_id}_v{version}.{extension}` (where extension is `md`, `txt`, or `pdf`).
*   **RETENTION**: Kept indefinitely, or deleted when the user manually deletes the repository or their account.
*   **ACCESS**: private (presigned URL access only).
*   **PRESIGNED**: Generated on-demand with a **15-minute expiration** window.

---

### 4. `user-exports`
*   **BUCKET**: `user-exports`
*   **PURPOSE**: Temporary storage for zipped bundles containing all generated outputs, compiled when the user requests a full export.
*   **CONTENTS**: `.zip` archive files.
*   **NAMING**: `exports/{user_id}/{export_job_id}/github-resume-pack.zip`
*   **RETENTION**: Automatically deleted 24 hours after creation.
*   **ACCESS**: private (presigned URL access only).
*   **PRESIGNED**: Generated on-demand with a **15-minute expiration** window.

---

## 6.2 Presigned URL Download Flow

Below is the step-by-step security and network flow for a user downloading their generated resume:

```
[Browser Client]             [Next.js BFF]            [FastAPI Backend]            [Cloudflare R2]
       │                           │                          │                           │
       │─── 1. Click Download ────►│                          │                           │
       │    (GET /outputs/[id])    │─── 2. Auth Proxy (JWT) ─►│                           │
       │                           │                          │                           │
       │                           │                          │── 3. Validate permissions │
       │                           │                          │   & log download event    │
       │                           │                          │                           │
       │                           │                          │── 4. Generate URL ────────│
       │                           │                          │   (boto3 sign_url)        │
       │                           │                          │                           │
       │                           │◄── 5. Return JSON ───────│                           │
       │                           │    {download_url, ...}   │                           │
       │                           │                          │                           │
       │◄── 6. Trigger Download ───│                          │                           │
       │    (window.open(url))     │                          │                           │
       │                           │                          │                           │
       │─────────────────────── 7. Direct HTTPS GET (S3 Request) ────────────────────────►│
       │                                                                                  │
       │◄────────────────────── 8. Streams File (Content-Disposition) ────────────────────│
```

### Flow Breakdown:
1.  **Trigger**: The user clicks the "Download Resume (.md)" button on the client interface.
2.  **API Call**: The client initiates an authorized `GET` request to the Next.js BFF at `/api/v1/outputs/{id}/download?format=md`. The BFF attaches the user's JWT credentials and forwards the request to the FastAPI backend.
3.  **Authentication & Audit Logging**: 
    *   The FastAPI backend verifies the user's session claims, ensuring they own the output resource linked to the request.
    *   The backend logs a download event to the `output_downloads` database table for security auditing.
4.  **Signature Generation**: The backend uses the AWS SDK S3 client (`boto3` in Python) to generate a presigned download URL.
    *   **Method**: `generate_presigned_url('get_object', Params={'Bucket': 'generated-outputs', 'Key': 'outputs/usr_123/job_456/out_789_v1.md', 'ResponseContentDisposition': 'attachment; filename="resume.md"'}, ExpiresIn=900)`
    *   *Note: Expiration is set to 900 seconds (15 minutes).*
5.  **Payload Return**: FastAPI returns the signed URL back through the BFF to the client in a JSON payload:
    ```json
    {
      "download_url": "https://generated-outputs.r2.cloudflarestorage.com/outputs/usr_123/job_456/out_789_v1.md?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...",
      "expires_at": "2026-06-18T19:26:00Z"
    }
    ```
6.  **Browser Download**: The client receives the payload and uses a temporary hidden anchor element (`<a href="download_url" download>`) to trigger a native browser download.
7.  **Direct Download**: The browser sends an HTTPS `GET` request directly to the Cloudflare R2 bucket using the presigned URL. R2 validates the signature and streams the file payload with an attachment header to start the download.

### Sharing Security:
*   If the user copies the presigned link and shares it with an unauthorized person, the link will function only within the **15-minute window**.
*   Once this window expires, Cloudflare R2 will reject any incoming requests with an `AccessDenied` error, rendering the link useless.
*   To share their achievements permanently, users must download the file locally and share it directly, or host it on a public portfolio path.
