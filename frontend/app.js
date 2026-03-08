const API_BASE = "http://localhost:8000";

const output = document.getElementById("output");

function readJobInputPayload() {
  return {
    job_link: document.getElementById("job_link").value || null,
    job_description: document.getElementById("job_description").value || null,
  };
}

function buildOutreachFormData() {
  const formData = new FormData();
  formData.append("recruiter_name", document.getElementById("recruiter_name").value);
  formData.append("recruiter_email", document.getElementById("recruiter_email").value);
  formData.append("recruiter_profile", document.getElementById("recruiter_profile").value);
  formData.append("job_link", document.getElementById("job_link").value || "");
  formData.append("job_description", document.getElementById("job_description").value || "");
  formData.append("resume_text", document.getElementById("resume_text").value || "");

  const resumeFileInput = document.getElementById("resume_file");
  if (resumeFileInput.files.length > 0) {
    formData.append("resume_file", resumeFileInput.files[0]);
  }

  return formData;
}

async function postJson(path, payload) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text);
  }

  return res.json();
}

async function postForm(path, formData) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text);
  }

  return res.json();
}

function printResult(title, data) {
  output.textContent = `${title}\n\n${JSON.stringify(data, null, 2)}`;
}

document.getElementById("btn-parse").addEventListener("click", async () => {
  try {
    const payload = readJobInputPayload();
    const data = await postJson("/parse-job", payload);
    printResult("Parsed Job", data);
  } catch (err) {
    printResult("Error", err.message);
  }
});

document.getElementById("btn-keywords").addEventListener("click", async () => {
  try {
    const payload = readJobInputPayload();
    const data = await postJson("/extract-keywords", payload);
    printResult("Extracted Keywords", data);
  } catch (err) {
    printResult("Error", err.message);
  }
});

document.getElementById("btn-draft").addEventListener("click", async () => {
  try {
    const formData = buildOutreachFormData();
    const data = await postForm("/draft-email-upload", formData);
    printResult("Draft Email", data);
  } catch (err) {
    printResult("Error", err.message);
  }
});

document.getElementById("btn-send").addEventListener("click", async () => {
  try {
    const formData = buildOutreachFormData();
    const data = await postForm("/send-email-upload", formData);
    printResult("Send Email", data);
  } catch (err) {
    printResult("Error", err.message);
  }
});
