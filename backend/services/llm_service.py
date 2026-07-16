"""
QuantumCopilot — LLM Service
Wraps Google Gemini API (google-genai SDK) with quantum-specialised system prompts.
Falls back to a rule-based demo mode when no API key is set or quota is exceeded.
"""
import os
import re
from google import genai
from google.genai import errors as genai_errors

SYSTEM_PROMPT = """You are QuantumCopilot, an expert quantum computing assistant.
When asked to generate a quantum circuit, you MUST:
1. Respond ONLY with valid Python code using Qiskit 1.x syntax.
2. The code must define a variable called `qc` which is a QuantumCircuit object.
3. Do NOT include any import statements — they are already handled.
4. Do NOT add measurements unless the user asks — just build the circuit.
5. Use only standard Qiskit gates: h, x, y, z, cx, ccx, rx, ry, rz, s, t, swap, cz, cp, etc.
6. Keep the circuit under 10 qubits.
7. End with the circuit being complete — no print statements.

Example output for "Bell state":
qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)

Example output for "GHZ state 3 qubits":
qc = QuantumCircuit(3)
qc.h(0)
qc.cx(0, 1)
qc.cx(0, 2)

Only output Python code, no markdown fences, no explanation text.
"""

TUTOR_SYSTEM_PROMPT = """You are QuantumCopilot, a friendly and knowledgeable quantum computing tutor.
You help users understand quantum computing concepts, circuits, algorithms, and phenomena.
- Use clear, accessible language with analogies when helpful.
- Format responses with markdown: use **bold**, bullet lists, and code blocks.
- When explaining gates, describe their mathematical effect and intuition.
- Be encouraging and patient.
- Keep responses focused and under 400 words unless a longer explanation is clearly needed.
"""

EXPLAIN_SYSTEM_PROMPT = """You are QuantumCopilot, a quantum circuit explainer.
Given Qiskit Python code for a quantum circuit, explain:
1. What the circuit accomplishes (high level)
2. What each gate does and why it is placed there
3. The quantum phenomena involved (superposition, entanglement, interference, etc.)
4. Practical applications of this circuit

Format your response with clear markdown sections.
"""

# ----- Demo mode circuits (no API key required) -----
DEMO_CIRCUITS = {
    "bell": """qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)""",
    "ghz": """qc = QuantumCircuit(3)
qc.h(0)
qc.cx(0, 1)
qc.cx(0, 2)""",
    "grover": """qc = QuantumCircuit(2)
qc.h([0, 1])
qc.cz(0, 1)
qc.h([0, 1])
qc.x([0, 1])
qc.cz(0, 1)
qc.x([0, 1])
qc.h([0, 1])""",
    "qft": """qc = QuantumCircuit(3)
qc.h(0)
qc.cp(3.14159/2, 0, 1)
qc.cp(3.14159/4, 0, 2)
qc.h(1)
qc.cp(3.14159/2, 1, 2)
qc.h(2)
qc.swap(0, 2)""",
    "teleportation": """qc = QuantumCircuit(3, 2)
qc.h(1)
qc.cx(1, 2)
qc.cx(0, 1)
qc.h(0)
qc.measure(0, 0)
qc.measure(1, 1)""",
    "superposition": """qc = QuantumCircuit(1)
qc.h(0)""",
    "entanglement": """qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)""",
    "deutsch": """qc = QuantumCircuit(2)
qc.x(1)
qc.h([0, 1])
qc.cx(0, 1)
qc.h(0)""",
}


def _demo_circuit(prompt: str) -> str:
    """Rule-based fallback circuit generator for demo mode."""
    p = prompt.lower()
    if "bell" in p or "entangl" in p:
        return DEMO_CIRCUITS["bell"]
    if "ghz" in p:
        return DEMO_CIRCUITS["ghz"]
    if "grover" in p:
        return DEMO_CIRCUITS["grover"]
    if "qft" in p or "fourier" in p:
        return DEMO_CIRCUITS["qft"]
    if "teleport" in p:
        return DEMO_CIRCUITS["teleportation"]
    if "superposition" in p:
        return DEMO_CIRCUITS["superposition"]
    if "deutsch" in p:
        return DEMO_CIRCUITS["deutsch"]
    return DEMO_CIRCUITS["superposition"]


def _demo_explain(code: str) -> str:
    if "cx" in code and "h" in code:
        return """## Bell State Circuit

**High-level purpose**: Creates a maximally entangled two-qubit state known as a Bell state.

### Gate Breakdown
- **H (Hadamard) on qubit 0**: Puts qubit 0 into equal superposition — it becomes ½|0⟩ + ½|1⟩.
- **CX (CNOT) on qubits 0→1**: Entangles qubits 0 and 1. If qubit 0 is |1⟩, qubit 1 is flipped.

### Quantum Phenomena
- **Superposition**: The Hadamard creates a qubit in both states simultaneously.
- **Entanglement**: After the CNOT, measuring one qubit instantly determines the other — no matter the distance.

### Applications
- Quantum teleportation protocols
- Quantum key distribution (BB84, E91)
- Benchmarking quantum hardware
"""
    return """## Quantum Circuit Explanation

This circuit implements a quantum algorithm using standard gates.

### Key Operations
- Gates manipulate qubit states through unitary transformations
- The circuit exploits superposition and potentially entanglement

### Applications
Quantum circuits like this are building blocks for quantum algorithms that can outperform classical computation for specific problems.
"""


def _get_client(api_key_override: str | None = None):
    """Return a configured Gemini client and model name, or (None, None) in demo mode."""
    api_key = api_key_override or os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        return None, None
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    api_version = 'v1beta' if '3.5' in model_name else 'v1'
    client = genai.Client(api_key=api_key, http_options={'api_version': api_version})
    return client, model_name


def _handle_api_error(e: Exception) -> str | None:
    """
    Return a user-friendly error string if it's a known API error,
    or None to let the caller re-raise.
    """
    err_str = str(e)
    if "503" in err_str or "UNAVAILABLE" in err_str:
        return (
            "⚠️ **Google Servers Overloaded** — The `gemini-3.5-flash` model is currently experiencing high demand.\n\n"
            "This is a temporary issue on Google's end. Please try again in a few minutes, or switch to `gemini-1.5-flash` in your backend `.env` file as a stable fallback."
        )
    return f"❌ **API Error Details:**\n\n```\n{err_str}\n```\n\nThis will help us debug the exact issue."


async def generate_circuit_code(prompt: str, api_key: str | None = None) -> str:
    """Generate Qiskit circuit code from a natural language prompt."""
    client, model_name = _get_client(api_key)
    if client is None:
        return _demo_circuit(prompt)

    try:
        full_prompt = f"{SYSTEM_PROMPT}\n\nGenerate a quantum circuit for: {prompt}"
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
        )
        code = response.text.strip()
        # Strip markdown fences if the model wraps in them
        code = re.sub(r"```(?:python)?", "", code).replace("```", "").strip()
        return code
    except Exception as e:
        friendly = _handle_api_error(e)
        if friendly:
            # Fall back to demo circuit but include the warning as a comment
            return f"# {friendly.splitlines()[0]}\n" + _demo_circuit(prompt)
        raise


async def explain_circuit(code: str, api_key: str | None = None) -> str:
    """Explain what a quantum circuit does."""
    client, model_name = _get_client(api_key)
    if client is None:
        return _demo_explain(code)

    try:
        full_prompt = f"{EXPLAIN_SYSTEM_PROMPT}\n\nExplain this quantum circuit:\n\n{code}"
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
        )
        return response.text.strip()
    except Exception as e:
        friendly = _handle_api_error(e)
        if friendly:
            return friendly
        raise


async def tutor_chat(messages: list[dict], api_key: str | None = None) -> str:
    """Multi-turn quantum tutor conversation."""
    client, model_name = _get_client(api_key)
    if client is None:
        return (
            "**Demo Mode Active** — Add your Gemini API key in `backend/.env` as `GEMINI_API_KEY` or paste it in the top right to enable the AI tutor.\n\n"
            "In the meantime, here are some things I can help with:\n"
            "- **Bell State**: Ask about entanglement\n"
            "- **Grover's Algorithm**: Ask about quantum search\n"
            "- **QFT**: Ask about the Quantum Fourier Transform"
        )

    try:
        # Build conversation history as a single prompt for Gemini
        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )
        full_prompt = f"{TUTOR_SYSTEM_PROMPT}\n\nConversation:\n{history_text}\n\nASSISTANT:"
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
        )
        return response.text.strip()
    except Exception as e:
        friendly = _handle_api_error(e)
        if friendly:
            return friendly
        raise
