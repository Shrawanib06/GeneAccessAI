// login and sign up

function showForm(formType) {
  document.getElementById('login-form').classList.add('hidden');
  document.getElementById('signup-form').classList.add('hidden');
  document.getElementById(formType + '-form').classList.remove('hidden');
}

// Chatbot functionality
const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const chatForm = document.getElementById('chat-form');
const typingIndicator = document.getElementById('typing-indicator');

let isProcessing = false;
let analysisComplete = false;

// Auto-scroll to bottom
function scrollToBottom() {
  if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add message to chat
function addMessage(content, isUser = false) {
  if (!chatMessages) return;
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;
  const contentDiv = document.createElement('div');
  contentDiv.className = 'message-content';
  contentDiv.innerHTML = content;
  messageDiv.appendChild(contentDiv);
  chatMessages.appendChild(messageDiv);
  scrollToBottom();
}

// Show/hide typing indicator
function showTyping(show) {
  if (!typingIndicator) return;
  typingIndicator.style.display = show ? 'block' : 'none';
  if (show) scrollToBottom();
}

// Add a function to show/hide analysis loading animation
function showAnalysisLoading(show) {
  let loadingDiv = document.getElementById('analysis-loading');
  if (show) {
    if (!loadingDiv) {
      loadingDiv = document.createElement('div');
      loadingDiv.id = 'analysis-loading';
      loadingDiv.innerHTML = `
        <div class="message bot">
          <div class="message-content" style="display: flex; align-items: center; gap: 10px;">
            <span class="spinner" style="width: 22px; height: 22px; border: 3px solid #007bff; border-top: 3px solid #e9ecef; border-radius: 50%; display: inline-block; animation: spin 1s linear infinite;"></span>
            <span>Analyzing your answers, please wait...</span>
          </div>
        </div>
      `;
      chatMessages.appendChild(loadingDiv);
      scrollToBottom();
    }
  } else {
    if (loadingDiv) {
      loadingDiv.remove();
    }
  }
}

// Add spinner animation CSS
const style = document.createElement('style');
style.innerHTML = `
@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}`;
document.head.appendChild(style);

// Loader for report generation
function showReportLoader(show) {
  let loaderDiv = document.getElementById('report-loader');
  if (show) {
    if (!loaderDiv) {
      loaderDiv = document.createElement('div');
      loaderDiv.id = 'report-loader';
      loaderDiv.className = 'report-loader';
      loaderDiv.innerHTML = `
        <div class="report-spinner"></div>
        <span class="report-loader-text">Generating your report, please wait...</span>
      `;
      chatMessages.appendChild(loaderDiv);
      scrollToBottom();
    }
  } else {
    if (loaderDiv) loaderDiv.remove();
  }
}

// Send message to server
async function sendMessage(message, suppressUserMessage = false) {
  if (!message.trim() || isProcessing) return;
  // Block 'results' and 'report' commands until analysis is complete
  const blockedCommands = ['results', 'report', 'summary', 'analysis', 'pdf', 'download report', 'get report'];
  if (!analysisComplete && blockedCommands.includes(message.trim().toLowerCase())) {
    addMessage('⚠️ Please answer all questions before requesting results or a report.', false);
    return;
  }
  isProcessing = true;
  if (sendBtn) sendBtn.disabled = true;
  if (!suppressUserMessage) {
    addMessage(message, true);
  }
  if (messageInput) messageInput.value = '';

  // Remove typing indicator for analysis step
  let showTypingForThis = true;
  const lastBotMsg = Array.from(chatMessages.querySelectorAll('.message.bot .message-content')).pop();
  let isLastQuestion = false;
  if (lastBotMsg && lastBotMsg.textContent && (
    lastBotMsg.textContent.includes('If you have a DNA test file') ||
    lastBotMsg.textContent.includes('Have you had any genetic testing before?')
  )) {
    showTypingForThis = false;
    isLastQuestion = true;
  }
  if (showTypingForThis) {
    showTyping(true);
  }

  // If this is the last question, show a thank you message before analysis
  if (isLastQuestion) {
    addMessage('Thank you for your answers. Generating your analysis...', false);
    showAnalysisLoading(true);
  }

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message: message })
    });
    const data = await response.json();
    showAnalysisLoading(false); // Hide loading animation when response arrives
    showTyping(false);
    // Show loader if analysis is complete but report is not yet ready
    if (data.success) {
      analysisComplete = !!data.analysis_complete;
      if (data.analysis_complete) {
        showReportLoader(true);
        setTimeout(() => { // Simulate report generation delay for UX
          showReportLoader(false);
          if (data.report_info) {
            showReportDownload(data.report_info);
          } else {
            addMessage('Your report is ready. Please check the Reports page.', false);
          }
        }, 2000); // Adjust delay as needed
      } else {
        addMessage(data.response);
      }
    } else {
      throw new Error(data.error || 'Unknown error');
    }
  } catch (error) {
    showAnalysisLoading(false);
    showTyping(false);
    showReportLoader(false);
    console.error('Chat error:', error);
    addMessage('❌ Sorry, there was an error processing your message. Please try again.');
  } finally {
    isProcessing = false;
    if (sendBtn) sendBtn.disabled = false;
    if (messageInput) messageInput.focus();
  }
}

// Show report download button
function showReportDownload(reportInfo) {
  if (!chatMessages) return;
  const reportDiv = document.createElement('div');
  reportDiv.className = 'message bot';
  reportDiv.innerHTML = `
    <div class="message-content">
      <p>Your comprehensive genetic risk assessment report has been generated successfully.</p>
      <button onclick="downloadReport('${reportInfo.download_url}')" class="download-btn">
        Download PDF Report
      </button>
      <p style="font-size: 12px; margin-top: 10px; color: #666;">
        <em>This report is for educational purposes only and should be reviewed with healthcare professionals.</em>
      </p>
    </div>
  `;
  chatMessages.appendChild(reportDiv);
  scrollToBottom();
}

// Download report
async function downloadReport(downloadUrl) {
  try {
    window.open(downloadUrl, '_blank');
  } catch (error) {
    console.error('Download error:', error);
    alert('Error downloading report. Please try again.');
  }
}

// Reset chat session
async function resetChat() {
  if (isProcessing) return;
  try {
    const response = await fetch('/api/chat/reset', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      }
    });
    const data = await response.json();
    if (data.success) {
      if (chatMessages) chatMessages.innerHTML = '';
      addMessage(data.response);
    }
  } catch (error) {
    console.error('Reset error:', error);
    addMessage('❌ Error resetting chat. Please refresh the page.');
  }
}

// Handle form submission
if (chatForm) {
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (message) {
      sendMessage(message);
    }
  });
}

// Handle Enter key
if (messageInput) {
  messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const message = messageInput.value.trim();
      if (message) {
        sendMessage(message);
      }
    }
  });
}

// Hide chat, show form initially
const patientFormContainer = document.getElementById('patient-info-form-container');
const chatbotSection = document.getElementById('chatbot-section');
if (chatMessages) chatMessages.innerHTML = '';
const patientForm = document.getElementById('patient-info-form');
if (patientForm) {
  patientForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    // Collect patient info
    const name = document.getElementById('patient_name').value.trim();
    const sex = document.getElementById('sex').value;
    const age = document.getElementById('age').value.trim();
    const dob = document.getElementById('dob').value;
    // Hide form, show chat
    if (patientFormContainer) patientFormContainer.style.display = 'none';
    if (chatbotSection) chatbotSection.style.display = '';
    if (chatMessages) chatMessages.innerHTML = '';
    // Send patient info to backend
    await fetch('/api/chat/patient_info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: name, sex, age, dob })
    });
    // Optionally, you can display the first question manually if you want:
    addMessage('Do you have a family history of genetic conditions? (yes/no)');
  });
}

// Show default welcome message if chat is empty
window.addEventListener('DOMContentLoaded', function () {
  if (chatMessages && chatMessages.children.length === 0) {
    addMessage("Welcome to GeneAccessAI. I'm Dr. GeneAccess. Let's begin with some basic information. What's your full name?", false);
  }
});

// Doctor-style question flow
const doctorQuestions = [
  "Do you have any family history of genetic disorders?",
  "Have you experienced seizures, developmental delay, etc.?",
  "Were there any abnormal growth patterns during childhood?",
  "Any known disorders in your ethnic group?",
  "Upload DNA test data if available (optional)."
];
let currentQuestion = 0;
let answers = [];

function showDoctorQuestion() {
  const questionContainer = document.getElementById('question-container');
  const answerInput = document.getElementById('answer-input');
  const fileUpload = document.getElementById('file-upload-container');
  const nextBtn = document.getElementById('next-btn');
  const submitBtn = document.getElementById('submit-btn');

  if (currentQuestion < doctorQuestions.length - 1) {
    questionContainer.textContent = doctorQuestions[currentQuestion];
    answerInput.value = '';
    answerInput.style.display = 'inline-block';
    fileUpload.style.display = 'none';
    nextBtn.style.display = 'inline-block';
    submitBtn.style.display = 'none';
  } else if (currentQuestion === doctorQuestions.length - 1) {
    // File upload question
    questionContainer.textContent = doctorQuestions[currentQuestion];
    answerInput.style.display = 'none';
    fileUpload.style.display = 'block';
    nextBtn.style.display = 'none';
    submitBtn.style.display = 'inline-block';
  }
}

document.addEventListener('DOMContentLoaded', function () {
  if (document.getElementById('doctor-form')) {
    showDoctorQuestion();
    document.getElementById('answer-input').addEventListener('keypress', function (e) {
      if (e.key === 'Enter') {
        nextQuestion();
      }
    });
    document.getElementById('doctor-form').addEventListener('submit', submitDoctorForm);
  }
});

function nextQuestion() {
  const answerInput = document.getElementById('answer-input');
  if (answerInput.value.trim() === '') return;
  answers.push(answerInput.value.trim());
  currentQuestion++;
  showDoctorQuestion();
}

function submitDoctorForm(e) {
  e.preventDefault();
  const fileInput = document.getElementById('dna-file');
  const formData = new FormData();
  // Add answers
  for (let i = 0; i < answers.length; i++) {
    formData.append('answer' + (i + 1), answers[i]);
  }
  // Add file if present
  if (fileInput && fileInput.files.length > 0) {
    formData.append('dna_file', fileInput.files[0]);
  }
  // Show loading message
  addMessage('Analyzing your information, please wait...', 'bot');
  fetch('/analyze', {
    method: 'POST',
    body: formData
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        addMessage('Prediction: ' + data.prediction, 'bot');
        addMessage('Details: ' + data.details, 'bot');
        if (data.report_url) {
          addMessage('Download your report: ', 'bot');
          const chatMessages = document.getElementById('chat-messages');
          const link = document.createElement('a');
          link.href = data.report_url;
          link.textContent = 'Download PDF Report';
          link.target = '_blank';
          chatMessages.appendChild(link);
        }
      } else {
        addMessage('Sorry, there was an error analyzing your data.', 'bot');
      }
    })
    .catch(() => {
      addMessage('Sorry, there was an error connecting to the server.', 'bot');
    });
}

// Add reset button next to send button
if (chatInput) {
  const resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.textContent = 'Reset';
  resetBtn.className = 'reset-btn';
  resetBtn.style.marginLeft = '0.5rem';
  resetBtn.onclick = resetChat;
  sendBtn.parentNode.insertBefore(resetBtn, sendBtn.nextSibling);
}