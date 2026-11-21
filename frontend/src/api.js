const API = '';  // Vite proxy handles /api -> localhost:8000

// ── Auth helpers ──────────────────────────────────────────────────────────────

function authHeaders() {
  const token = localStorage.getItem('frontdesk_token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

export async function loginAgent(email, password) {
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Invalid email or password');
  }
  const data = await res.json();
  localStorage.setItem('frontdesk_token', data.access_token);
  return data;
}

export function logoutAgent() {
  localStorage.removeItem('frontdesk_token');
}

export async function getMe() {
  const res = await fetch(`${API}/api/auth/me`, { headers: authHeaders() });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchAgents() {
  const res = await fetch(`${API}/api/agents`);
  if (!res.ok) throw new Error('Failed to fetch agents');
  return res.json();
}

export async function fetchTickets(status = '') {
  const url = status ? `${API}/api/tickets?status=${status}` : `${API}/api/tickets`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch tickets');
  return res.json();
}

export async function fetchTicket(id) {
  const res = await fetch(`${API}/api/tickets/${id}`);
  if (!res.ok) throw new Error('Ticket not found');
  return res.json();
}

export async function createTicket(data) {
  const res = await fetch(`${API}/api/tickets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create ticket');
  return res.json();
}

export async function claimTicket(ticketId, agentId) {
  const res = await fetch(`${API}/api/tickets/${ticketId}/claim`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ agent_id: agentId }),
  });
  if (res.status === 409) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Ticket already claimed by another agent');
  }
  if (!res.ok) {
    throw new Error('Failed to claim ticket');
  }
  return res.json();
}

export async function fetchMessages(ticketId, scope = 'agent') {
  const res = await fetch(`${API}/api/tickets/${ticketId}/messages?scope=${scope}`);
  if (!res.ok) throw new Error('Failed to fetch messages');
  return res.json();
}

export async function postMessage(ticketId, messageData) {
  const res = await fetch(`${API}/api/tickets/${ticketId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(messageData),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to post message');
  }
  return res.json();
}

export async function fetchAuditLogs(ticketId) {
  const res = await fetch(`${API}/api/tickets/${ticketId}/audit`);
  if (!res.ok) throw new Error('Failed to fetch audit trail');
  return res.json();
}

// Module 4: SLA Engine (INC-0327)
export async function updatePriority(ticketId, priority, agentId) {
  const res = await fetch(`${API}/api/tickets/${ticketId}/priority`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ priority, agent_id: agentId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update priority');
  }
  return res.json();
}

export async function resolveTicket(ticketId, agentId) {
  const res = await fetch(`${API}/api/tickets/${ticketId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ agent_id: agentId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to resolve ticket');
  }
  return res.json();
}

// Module 5: Lifecycle Policies (REQ-SLA-04 & REQ-SLA-05)
export async function reopenTicket(ticketId, agentId, reason = '') {
  const res = await fetch(`${API}/api/tickets/${ticketId}/reopen`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ agent_id: agentId, reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to reopen ticket');
  }
  return res.json();
}

export async function triggerAutoClose() {
  const res = await fetch(`${API}/api/tickets/auto-close`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to evaluate auto-close policy');
  return res.json();
}

