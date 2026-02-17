# 🔌 AI Circuit Generator & Schematic Drawer

An intelligent **SPICE circuit generator + schematic drawer** powered by **Google Gemini AI**, voice recognition, and automatic circuit visualization.

This tool can:

✨ Generate SPICE code from text or voice  
🎙️ Convert speech → circuit  
🧠 Validate circuit errors  
📐 Automatically draw schematic diagrams  
💾 Save & load circuits  
🧪 Run test examples  

---

# 🚀 Features

## 🧠 AI Circuit Generation
Generate valid **SPICE netlist** using Google Gemini from:
- Text description
- Voice description

---

## 📐 Automatic Schematic Drawing
- Parses SPICE netlist
- Detects circuit path
- Draws schematic using `schemdraw`
- Supports:
  - Resistor
  - Capacitor
  - Inductor
  - Diode / Zener
  - BJT
  - MOSFET
  - Op-Amp
  - ICs
  - Voltage Source

---

## 🎙️ Voice Recognition
Speak in Persian → Automatically generates circuit.

---

## 🧪 Circuit Validation

Detects:

- ❌ Short circuit  
- ❌ Invalid resistor values  
- ⚠️ Electrolytic capacitor polarity warning  

Stops drawing if critical errors exist.

---

## 💾 Save & Load Circuits

- Save circuits as `.json`
- Load saved circuits
- List saved circuits
- Timestamp + description stored

---

# 📦 Requirements

Install dependencies:

```bash
pip install google-generativeai SpeechRecognition schemdraw pyaudio
```

> ⚠️ On Windows you may need:
```
pip install pipwin
pipwin install pyaudio
```

---

# 🔑 Setup Gemini API Key

Set your API key:

```bash
export GEMINI_API_KEY="YOUR_API_KEY"
```

Windows:

```bash
set GEMINI_API_KEY=YOUR_API_KEY
```

---

# ▶️ Run Program

```bash
python main.py
```

---

# 📋 Menu

```
1️⃣ Generate Circuit (Text)
2️⃣ Generate Circuit (Voice)
3️⃣ Test Examples
4️⃣ Load Circuit
5️⃣ List Saved Circuits
0️⃣ Exit
```

---

# 🧪 Example Circuits

Includes built-in examples:

- Simple RC circuit  
- BJT transistor circuit  
- Parallel resistor network  
- Diode circuit  
- Op-Amp circuit  
- IC 555 timer  
- MOSFET circuit  
- Complex mixed circuit  

---

# 📐 Supported SPICE Format

```
R<name> node1 node2 value
C<name> node1 node2 value
L<name> node1 node2 value
V<name> node+ node- value
D<name> anode cathode model
Q<name> C B E model
M<name> D G S B model
U<name> ... IC / OpAmp
```

---

# ⚠️ Notes

- Data stored in memory until saved
- Drawing stops if critical errors detected
- Voice recognition requires microphone
- API key required for AI generation

---

# 🛠 Architecture

## Core Modules

### 🔍 Netlist Parser
Converts SPICE text → structured components.

### 📊 Circuit Graph Builder
Finds circuit path & parallel branches.

### ⚠️ Validator
Checks electrical errors & warnings.

### 📐 Schematic Drawer
Draws automatic schematic layout.

### 🧠 Gemini Generator
Generates SPICE from natural language.

### 🎙️ Voice Input
Speech → text → circuit.

### 💾 Storage System
Save / Load JSON circuits.


---

# ❤️ Example Output

```
💡 SPICE Code Generated
⚠️ Warning: Electrolytic capacitor polarity
📐 Drawing schematic...
✅ Circuit drawn successfully
```


# ⭐ If you like this project

Give it a ⭐ on GitHub and build crazy circuits with AI 🔥
