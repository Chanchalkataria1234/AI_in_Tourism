async function sendMessage() {
    const input = document.getElementById('user-input');
    const chatBox = document.getElementById('chat-box');
    const message = input.value.trim();

    if (!message) return;

    // Render User Message
    chatBox.innerHTML += `<div class="message user-message">${message}</div>`;
    input.value = '';

    // Show Loading
    const loadingId = "loading-" + Date.now();
    chatBox.innerHTML += `<div class="message bot-message" id="${loadingId}">Typing...</div>`;
    chatBox.scrollTop = chatBox.scrollHeight;

    // API Call
    const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message })
    });

    const data = await response.json();
    
    // Replace Loading with AI Response
    document.getElementById(loadingId).innerHTML = data.reply.replace(/\n/g, "<br>");
    chatBox.scrollTop = chatBox.scrollHeight;
}

// Allow "Enter" key to send
document.getElementById('user-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});