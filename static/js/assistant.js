(() => {
  const launcher = document.querySelector("#assistant-launcher");
  const panel = document.querySelector("#assistant-panel");
  if (!launcher || !panel) return;
  const messages = document.querySelector("#assistant-messages");
  const form = document.querySelector("#assistant-form");
  const input = document.querySelector("#assistant-input");
  const organization = document.querySelector("#assistant-organization");
  const history = [];

  const addMessage = (text, role, confirmation) => {
    const bubble = document.createElement("p");
    bubble.className = `assistant-message assistant-${role}`;
    bubble.textContent = text;
    messages.appendChild(bubble);
    if (confirmation) {
      const button = document.createElement("button");
      button.className = "assistant-confirm";
      button.textContent = "Confirm operation";
      button.onclick = () => send("", confirmation, button);
      messages.appendChild(button);
    }
    messages.scrollTop = messages.scrollHeight;
  };

  const send = async (message, confirmedAction = null, button = null) => {
    if (!organization.value) return addMessage("No accessible organization is available.", "bot");
    if (button) button.disabled = true;
    addMessage(confirmedAction ? "Confirming operation..." : message, "user");
    const response = await fetch("/assistant/chat/", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value},
      body: JSON.stringify({message, organization_id: organization.value, history, confirmed_action: confirmedAction}),
    });
    const data = await response.json();
    addMessage(data.reply || data.error || "The assistant could not respond.", "bot", data.confirmation);
    if (!confirmedAction) history.push({role: "user", content: message});
    history.push({role: "assistant", content: data.reply || data.error || ""});
  };

  launcher.onclick = () => { panel.hidden = false; input.focus(); };
  document.querySelector("#assistant-close").onclick = () => { panel.hidden = true; };
  form.onsubmit = (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    send(message);
  };
})();
