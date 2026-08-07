#ifndef USBTMCSCOPE_H
#define USBTMCSCOPE_H

#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <cctype>
#include <stdexcept>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <linux/usb/tmc.h>

class USBTMCScope {
private:
    std::string devicePath;
    int fd = -1;

    // Low-level: write raw bytes to the device.
    void rawWrite(const char* data, size_t len) {
        ssize_t written = write(fd, data, len);
        if (written < 0 || static_cast<size_t>(written) != len) {
            throw std::runtime_error("Write error on " + devicePath + ": " +
                                      std::strerror(errno));
        }
    }

    // Low-level: read up to bufSize bytes, return how many we got.
    ssize_t rawRead(char* buf, size_t bufSize) {
        ssize_t n = read(fd, buf, bufSize);
        if (n < 0) {
            throw std::runtime_error("Read error on " + devicePath + ": " +
                                      std::strerror(errno));
        }
        return n;
    }

public:
    USBTMCScope(const std::string& path = "/dev/usbtmc0") : devicePath(path) {
        fd = open(devicePath.c_str(), O_RDWR);
        if (fd < 0) {
            throw std::runtime_error("Failed to open " + devicePath + ": " +
                                      std::strerror(errno) +
                                      " (check permissions / udev rules)");
        }

        // Clear any leftover state from a previous transfer that didn't
        // complete cleanly (e.g. a program that crashed or was killed
        // mid-read). Not fatal if unsupported by the driver — just means
        // we skip the reset and proceed as before.
        if (ioctl(fd, USBTMC_IOCTL_CLEAR) < 0) {
            std::cerr << "Note: USBTMC_IOCTL_CLEAR not supported/failed ("
                      << std::strerror(errno) << ") — continuing anyway.\n";
        }

        // Bump the driver's per-transfer timeout — large transfers over an
        // emulated USB controller (e.g. VirtualBox EHCI) can take longer
        // than the ~5s kernel default, causing short reads.
#ifdef USBTMC_IOCTL_CTRL_TIMEOUT
        {
            __u32 timeoutMs = 30000; // 30 seconds
            if (ioctl(fd, USBTMC_IOCTL_CTRL_TIMEOUT, &timeoutMs) < 0) {
                std::cerr << "Note: could not raise USBTMC timeout ("
                          << std::strerror(errno) << ").\n";
            }
        }
#endif
    }

    ~USBTMCScope() {
        if (fd >= 0) close(fd);
    }

    USBTMCScope(const USBTMCScope&) = delete;
    USBTMCScope& operator=(const USBTMCScope&) = delete;

    // Text query — same as before, for *IDN? etc.
    std::string query(const std::string& command) {
        std::string cmd = command;
        if (cmd.empty() || cmd.back() != '\n') cmd += '\n';
        rawWrite(cmd.data(), cmd.size());

        char buf[4096];
        ssize_t n = rawRead(buf, sizeof(buf) - 1);
        buf[n] = '\0';
        std::string response(buf, n);
        while (!response.empty() &&
               (response.back() == '\n' || response.back() == '\r' ||
                response.back() == ' '  || response.back() == '\t')) {
            response.pop_back();
        }
        return response;
    }

    // Binary query for block-format transfers. Kept as general-purpose
    // infrastructure (e.g. for waveform dumps later) even though the
    // screenshot feature that originally used it has been removed.
    // Handles IEEE 488.2 definite-length block format:
    //   '#' <N> <N digits of length> <that many raw bytes>
    std::vector<char> queryBinary(const std::string& command,
                                   size_t maxExpectedBytes = 8 * 1024 * 1024) {
        std::string cmd = command;
        if (cmd.empty() || cmd.back() != '\n') cmd += '\n';
        rawWrite(cmd.data(), cmd.size());

        std::vector<char> buf(maxExpectedBytes);
        ssize_t n = rawRead(buf.data(), buf.size());
        if (n < 2 || buf[0] != '#') {
            throw std::runtime_error(
                "Unexpected response — expected IEEE 488.2 block data "
                "starting with '#'. Got " + std::to_string(n) + " bytes.");
        }

        int numLenDigits = buf[1] - '0';
        if (numLenDigits < 1 || numLenDigits > 9) {
            throw std::runtime_error("Malformed block header from device.");
        }

        size_t headerSize = 2 + static_cast<size_t>(numLenDigits);
        while (static_cast<size_t>(n) < headerSize) {
            ssize_t more = rawRead(buf.data() + n, buf.size() - n);
            if (more <= 0) throw std::runtime_error(
                "Device closed connection before sending full header.");
            n += more;
        }

        std::string lenStr(buf.data() + 2, numLenDigits);
        size_t payloadLen = std::stoul(lenStr);

        std::vector<char> data(buf.begin() + headerSize, buf.begin() + n);

        const size_t chunkSize = 4096;
        std::vector<char> chunkBuf(chunkSize);

        while (data.size() < payloadLen) {
            size_t want = std::min(chunkSize, payloadLen - data.size());
            ssize_t got = rawRead(chunkBuf.data(), want);
            if (got <= 0) {
                if (data.size() >= payloadLen - 16) break;
                throw std::runtime_error(
                    "Device closed connection early (" + std::to_string(data.size()) +
                    " of " + std::to_string(payloadLen) + " bytes received).");
            }
            data.insert(data.end(), chunkBuf.begin(), chunkBuf.begin() + got);
        }

        return data;
    }

    bool isConnected() const { return fd >= 0; }
    const std::string& path() const { return devicePath; }

    // =====================================================================
    // SCPI COMMAND LAYER — mirrors the Python `Scope` class in the PyQt6
    // reference app. Nothing above this line was touched.
    // =====================================================================

    // Write-only helper (mirrors Python's fire-and-forget scope.write(...))
    void writeCommand(const std::string& command) {
        std::string cmd = command;
        if (cmd.empty() || cmd.back() != '\n') cmd += '\n';
        rawWrite(cmd.data(), cmd.size());
    }

    /// Queries and returns the *IDN identity string.
    std::string getIdn() {
        return query("*IDN?");
    }

    /// Puts the scope into continuous capture execution.
    void run() { writeCommand(":RUN"); }

    /// Freezes the scope acquisition state.
    void stop() { writeCommand(":STOP"); }

    /// Sets the coupling mode of the specified channel: AC, DC, GND.
    void configureCoupling(int channel, const std::string& coupling) {
        writeCommand(":CHANnel" + std::to_string(channel) + ":DISPlay ON");
        writeCommand(":CHANnel" + std::to_string(channel) + ":COUPling " + coupling);
    }

    /// Sets the probe ratio of the specified analog channel.
    void configureProbe(int channel, const std::string& attenuation) {
        writeCommand(":CHANnel" + std::to_string(channel) + ":DISPlay ON");
        writeCommand(":CHANnel" + std::to_string(channel) + ":PROBe " + attenuation);
    }

    /// Turns waveform invert on/off for the specified channel (toggles current state).
    void toggleInvert(int channel) {
        writeCommand(":CHANnel" + std::to_string(channel) + ":DISPlay ON");

        std::string current = query(":CHANnel" + std::to_string(channel) + ":INVert?");
        std::string newStatus = (current == "1" || current == "ON") ? "OFF" : "ON";

        writeCommand(":CHANnel" + std::to_string(channel) + ":INVert " + newStatus);
    }

    /// Sets the vertical scale of the specified channel (V/div).
    void voltageScale(int channel, double scale) {
        writeCommand(":CHANnel" + std::to_string(channel) + ":DISPlay ON");
        writeCommand(":CHANnel" + std::to_string(channel) + ":SCAle " + std::to_string(scale));
    }

    /// Sets the trigger level of the Edge trigger.
    void triggerLevel(double level) {
        writeCommand(":TRIGger:PULSe:LEVel " + std::to_string(level));
    }

    /// Sets trigger sweep mode: AUTO, NORMAL, or SINGLE.
    void setTriggerSweep(std::string mode) {
        for (auto& c : mode) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
        writeCommand(":TRIGger:SWEep " + mode);
    }

    /// Triggers the oscilloscope Autoset function and waits for completion.
    void triggerAutoset() {
        writeCommand(":AUToset");
        query("*OPC?");
    }

    /// Sets the edge trigger source. Accepts 'CHAN1'..'CHAN4', 'CH1'..'CH4', or 'EXT'.
    void setTriggerSource(std::string source) {
        for (auto& c : source) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
        if (source.rfind("CH", 0) == 0 && source.rfind("CHAN", 0) != 0) {
            source = "CHAN" + source.substr(2);
        }
        writeCommand(":TRIGger:EDGe:SOURce " + source);
    }

    /// Sets the edge trigger slope direction. Accepts RISING/POS, FALLING/NEG, BOTH/RFAL.
    void setTriggerSlope(std::string slope) {
        for (auto& c : slope) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
        if (slope == "RISING" || slope == "POS") slope = "POSitive";
        else if (slope == "FALLING" || slope == "NEG") slope = "NEGative";
        else if (slope == "BOTH" || slope == "RFAL") slope = "RFALl";
        writeCommand(":TRIGger:EDGe:SLOPe " + slope);
    }

    /// Sets the trigger signal coupling: AC, DC, LFR, HFR.
    void setTriggerCoupling(std::string coupling) {
        for (auto& c : coupling) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
        writeCommand(":TRIGger:COUPling " + coupling);
    }

    /// Configures the horizontal time base scale (seconds/div).
    void timeScale(double scale) {
        writeCommand(":TIMebase:SCALe " + std::to_string(scale));
    }

    /// Closes the device early (object can still be destroyed safely after this).
    void disconnect() {
        if (fd >= 0) {
            close(fd);
            fd = -1;
            std::cerr << "Instrument disconnected.\n";
        }
    }
};

#endif // USBTMCSCOPE_H
