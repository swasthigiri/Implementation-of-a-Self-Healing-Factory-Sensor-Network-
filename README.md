# LUMEN CORE — Self-Healing Factory Sensor Mesh with STM32 Gateway

An infrastructure-free, low-cost Industrial IoT (IIoT) condition-monitoring network built using ESP-NOW and an STM32 microcontroller, featuring automated per-node link quality estimation, dynamic self-healing routing, and a real-time browser dashboard[cite: 1, 2].

## 👥 Authors & Academic Details
* **Students:** Sri Swasthi S (9924005031), Harikrishnan Veerapan (9924005267), Ajay Krishnan (9924005013), Sree Lekshmi S (9924005373)[cite: 1]
* **Degree & Specialization:** Bachelor of Engineering in Electronics and Communication Engineering (Embedded Systems)[cite: 1]
* **Institution:** Kalasalingam Academy of Research and Education (KARE), Krishnankoil, Tamil Nadu, India[cite: 1]
* **Guides:** Mr. Bhargav (External Guide, Simask Pvt Ltd) | Prof. Mrs. Loyola Jasmine (Internal Guide, Dept. of ECE, KARE)[cite: 1]

---

## 📌 Project Overview
Industrial factory floors present harsh radio environments with moving machinery, metallic barriers, and electromagnetic noise that cause intermittent radio link drops[cite: 2]. Conventional star topologies drop data silently during these events[cite: 2]. **LUMEN CORE** solves this by establishing a decentralized, self-healing wireless sensor mesh over raw **ESP-NOW** (requiring no routers, Wi-Fi access points, or cloud brokers)[cite: 1, 2]. 

Each sensor node independently monitors its own packet-delivery ratio (PDR) using a sliding window[cite: 1]. If performance drops below 70%, the node automatically reroutes traffic through a backup neighbor ring ($\text{A} \to \text{B} \to \text{C} \to \text{A}$) and automatically recovers the direct path once the link is restored[cite: 1].

---

## 🛠️ System Architecture & Hardware Stack

* **Node G (Gateway / Mesh Root):** ESP32 #1 running an IR Flame sensor, receiving peer packets, and piping lines to the STM32 via UART[cite: 1].
* **Node A:** ESP32 measuring temperature and humidity via a **DHT11** sensor (GPIO4)[cite: 1].
* **Node B:** ESP32 monitoring machine vibration using an **SW-420** sensor module (GPIO34)[cite: 1].
* **Node C:** ESP32 monitoring gas/smoke concentration using an **MQ-2** sensor (GPIO32/GPIO35)[cite: 1].
* **STM32F446RE (Nucleo-64 Controller):** Assembles incoming UART packets via interrupt service routines, drives hardware indicator LED **LD2** on `PA5` when relayed traffic is detected, and mirrors the stream to a PC over the ST-LINK Virtual COM Port[cite: 1].
* **Browser Dashboard:** A single-page HTML/JS application leveraging the **Web Serial API** (Chrome/Edge) to render live values, packet logs, sparklines, and an interactive SVG topology map[cite: 1].

---

## 📂 Repository Contents
* `nodeA.py` – MicroPython firmware for Node A (DHT11 + self-healing logic)[cite: 6]
* `nodeB.py` – MicroPython firmware for Node B (SW-420 vibration analyzer + self-healing logic)[cite: 5]
* `nodeC.py` – MicroPython firmware for Node C (MQ-2 gas/smoke sensor + self-healing logic)[cite: 8]
* `nodeG.py` – MicroPython firmware for the Gateway ESP32 (UART bridge + flame sensor)[cite: 7]
* `lumen_dashboard_1.html` – Web Serial API live network monitoring dashboard[cite: 4]
* `stm32_main.c` (or project source files) – STM32 HAL C interrupt-driven UART controller firmware[cite: 1]
* Project Report (`.docx` / PDF) and Presentation (`.pptx`)[cite: 1, 2]

---

## 🚀 Getting Started & Usage

1. **Flash MicroPython:** Flash the generic MicroPython firmware onto the ESP32 boards using **Thonny IDE** or `esptool`[cite: 1, 5, 6, 7, 8].
2. **Upload Scripts:** Save respective scripts as `main.py` onto Nodes A, B, C, and Gateway G[cite: 5, 6, 7, 8].
3. **Flash STM32 Controller:** Open the STM32 project in **STM32CubeIDE**, compile, and flash the HAL C code onto the Nucleo-F446RE board[cite: 1].
4. **Launch Dashboard:** Open `lumen_dashboard_1.html` in Google Chrome or Microsoft Edge, click **Connect to STM32**, and select the ST-LINK Virtual COM Port (115200 baud)[cite: 1, 4].
5. **Fault-Injection Test:** Press the BOOT button (`GPIO0`) on any ESP32 node to simulate a broken direct link; observe the automatic transition to `RELAY` mode on the dashboard, node LED, and STM32 LD2 indicator[cite: 1, 5, 6, 8].
