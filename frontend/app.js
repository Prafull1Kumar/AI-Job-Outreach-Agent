const API_BASE = "http://localhost:8000";

const output = document.getElementById("output");

function readPayload() {
  return {
    recruiter_name: document.getElementById("recruiter_name").value,
    recruiter_email: document.getElementById("recruiter_email").value,
    recruiter_profile: document.getElementById("recruiter_profile").value,
    job_description: document.getElementById("job_description").value,
    resume_text: document.getElementById("resume_text").value,
  };
}

async function post(path, payload) {
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

function printResult(title, data) {
  output.textContent = `${title}\n\n${JSON.stringify(data, null, 2)}`;
}

document.getElementById("btn-parse").addEventListener("click", async () => {
  try {
    const payload = readPayload();
    const data = await post("/parse-job", payload);
    printResult("Parsed Job", data);
  } catch (err) {
    printResult("Error", err.message);
  }
});

document.getElementById("btn-draft").addEventListener("click", async () => {
  try {
    const payload = readPayload();
    const data = await post("/draft-email", payload);
    printResult("Draft Email", data);
  } catch (err) {
    printResult("Error", err.message);
  }
});

document.getElementById("btn-send").addEventListener("click", async () => {
  try {
    const payload = readPayload();
    const data = await post("/send-email", payload);
    printResult("Send Email", data);
  } catch (err) {
    printResult("Error", err.message);
  }
});
