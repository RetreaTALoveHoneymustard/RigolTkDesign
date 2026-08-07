// =========================================================================
// RigolDisplay.cpp
// -------------------------------------------------------------------------
// Same widget layout/styling as the original test_display_only build, but
// every control now calls a real USBTMCScope instance instead of just
// logging a message — this is the C++ equivalent of ScopeApp driving Scope
// in the PyQt6 reference app.
//
// Dropped vs. the display-only test and the Python reference:
//   - Presets (save/load/delete) — removed to keep this manageable, per
//     your go-ahead. Easy to add back later if you want it.
//   - Capture Screenshot / Live View — both depended on captureScreenshot(),
//     which you're abandoning, so there's nothing left for them to call.
//
// Build (Qt6 Widgets only):
//   g++ -std=c++17 -fPIC $(pkg-config --cflags Qt6Widgets) \
//       RigolDisplay.cpp -o RigolDisplay \
//       $(pkg-config --libs Qt6Widgets)
// (You said you're setting up CMake yourself — ping me when you want help
// wiring AUTOMOC/AUTOUIC for this.)
// =========================================================================

#include "USBTMCScope.h"

#include <QApplication>
#include <QMainWindow>
#include <QWidget>
#include <QLabel>
#include <QTextEdit>
#include <QComboBox>
#include <QLineEdit>
#include <QPushButton>
#include <QRadioButton>
#include <QButtonGroup>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QGridLayout>
#include <QDateTime>
#include <QFont>
#include <QScrollBar>
#include <QCloseEvent>

#include <memory>
#include <map>
#include <exception>

class RigolScopeApp : public QMainWindow {
    Q_OBJECT

public:
    explicit RigolScopeApp(QWidget* parent = nullptr) : QMainWindow(parent) {
        setWindowTitle("Rigol Oscilloscope Controller");
        resize(1100, 750);

        channelFont_ = QFont("Candara Light", 14, QFont::Bold);
        defaultFont_ = QFont("Yu Gothic UI Semilight", 12, QFont::Bold);
        buttonFont_ = QFont("Yu Gothic UI Semilight", 8, QFont::Bold);

        applyStylesheets();
        buildUi();

        logToTerminal("Welcome to Rigol GUI (C++ / Qt6).");
        logToTerminal("Oscilloscope type required: DHO800++");
    }

protected:
    void closeEvent(QCloseEvent* event) override {
        if (oscilloscope_) {
            try {
                oscilloscope_->disconnect();
            } catch (...) {
                // best-effort cleanup on exit
            }
        }
        event->accept();
    }

private:
    // =====================================================================
    // UI CONSTRUCTION
    // =====================================================================
    void applyStylesheets() {
        setStyleSheet(R"(
            QMainWindow { background-color: #303030; }
            QWidget { background-color: #303030; color: #ffffff; }
            QGroupBox {
                border: 1px solid #555555;
                border-radius: 4px;
                margin-top: 12px;
                background-color: #303030;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QLabel { background-color: #1e1e1e; color: #ffffff; padding: 2px; }
            QLineEdit { background-color: #1a1a1a; color: #00ff00; border: 1px solid #555555; }
            QComboBox { background-color: #1e1e1e; color: #ffffff; }
        )");
    }

    void buildUi() {
        const QString radioStyle = R"(
            QRadioButton { color: black; }
            QRadioButton:checked { color: yellow; font-weight: bold; }
        )";

        auto* central = new QWidget(this);
        setCentralWidget(central);
        auto* mainLayout = new QHBoxLayout(central);
        mainLayout->setContentsMargins(10, 10, 10, 10);

        auto* leftColumn = new QWidget();
        auto* leftLayout = new QVBoxLayout(leftColumn);
        leftLayout->setContentsMargins(5, 5, 5, 5);

        auto* rightColumn = new QWidget();
        auto* rightLayout = new QVBoxLayout(rightColumn);
        rightLayout->setContentsMargins(5, 5, 5, 5);

        mainLayout->addWidget(leftColumn, 4);
        mainLayout->addWidget(rightColumn, 1);
        // ----Waveform Display Placeholder----
        auto* waveformDisplay = new QLabel();
        waveformDisplay->setStyleSheet("background-color: #000000; border: 1px solid #555555;");
        waveformDisplay->setMinimumHeight(300);
        leftLayout->addWidget(waveformDisplay);
        
        // ----Terminal Frame----
        auto* terminalFrame = new QGroupBox("Terminal");
        terminalFrame->setFont(channelFont_);
        auto* terminalLayout = new QVBoxLayout(terminalFrame);
        leftLayout->addWidget(terminalFrame);

        auto* bottomTaskbarFrame = new QWidget();
        auto* bottomGrid = new QGridLayout(bottomTaskbarFrame);
        terminalLayout->addWidget(bottomTaskbarFrame);

        // -----Setup Elements-------- //
        auto* lblVoltDivCh1 = new QLabel("VOLT/DIVIDE");
        lblVoltDivCh1->setFont(buttonFont_);
        voltDiv_ = new QComboBox();
        voltDiv_->setFont(buttonFont_);
        voltDiv_->addItems({"100 mV", "200 mV", "500 mV", "1 V", "2 V", "10 V"});
        connect(voltDiv_, &QComboBox::currentIndexChanged, this, [this](int) { changeVoltDiv(); });

        auto* lblCoupling = new QLabel("COUPLING");
        lblCoupling->setFont(buttonFont_);
        coupChannel_ = new QComboBox();
        coupChannel_->setFont(buttonFont_);
        coupChannel_->addItems({"AC", "DC", "GND"});
        connect(coupChannel_, &QComboBox::currentIndexChanged, this, [this](int) { changeCoupling(); });

        auto* lblProbeConf = new QLabel("PROBE");
        lblProbeConf->setFont(buttonFont_);
        probeConfigChannel_ = new QComboBox();
        probeConfigChannel_->setFont(buttonFont_);
        probeConfigChannel_->addItems({"X0.1", "X0.2", "X0.5", "X1", "X2", "X5", "X10"});
        connect(probeConfigChannel_, &QComboBox::currentIndexChanged, this, [this](int) { probeSetting(); });

        // ----Channel radio buttons----
        radCh1_ = new QRadioButton("Configure CH1");
        radCh2_ = new QRadioButton("Configure CH2");
        radCh3_ = new QRadioButton("Configure CH3");
        radCh4_ = new QRadioButton("Configure CH4");
        for (auto* rb : {radCh1_, radCh2_, radCh3_, radCh4_}) {
            rb->setFont(buttonFont_);
            rb->setStyleSheet(radioStyle);
        }
        radCh1_->setChecked(true);

        channelGroup_ = new QButtonGroup(this);
        channelGroup_->addButton(radCh1_, 1);
        channelGroup_->addButton(radCh2_, 2);
        channelGroup_->addButton(radCh3_, 3);
        channelGroup_->addButton(radCh4_, 4);
        connect(channelGroup_, &QButtonGroup::idClicked, this, [this](int id) {
            activeChannel_ = id;
        });

        btnInvert_ = new QPushButton("INVERT");
        btnInvert_->setFont(buttonFont_);
        btnInvert_->setStyleSheet(
            "QPushButton { background-color: #d8cf48; color: #3c0854; border: 0; }"
            "QPushButton:hover { background-color: #f2e640; color: #230332; }");
        btnInvert_->setEnabled(false);
        connect(btnInvert_, &QPushButton::clicked, this, [this] { invertSignal(); });

        // -----Log frame-------
        terminalLog_ = new QTextEdit();
        terminalLog_->setReadOnly(true);
        terminalLog_->setStyleSheet("background-color: #000000; color: #00FF00;");
        terminalLog_->setFont(QFont("Courier New", 10));
        terminalLog_->setMinimumWidth(500);
        terminalLog_->setMinimumHeight(220);

        bottomGrid->addWidget(radCh1_, 0, 0);
        bottomGrid->addWidget(radCh2_, 1, 0);
        bottomGrid->addWidget(radCh3_, 2, 0);
        bottomGrid->addWidget(radCh4_, 3, 0);
        bottomGrid->addWidget(btnInvert_, 1, 1);
        bottomGrid->addWidget(lblVoltDivCh1, 0, 1);
        bottomGrid->addWidget(voltDiv_, 0, 2);
        bottomGrid->addWidget(lblCoupling, 2, 1);
        bottomGrid->addWidget(coupChannel_, 2, 2);
        bottomGrid->addWidget(lblProbeConf, 3, 1);
        bottomGrid->addWidget(probeConfigChannel_, 3, 2);
        bottomGrid->addWidget(terminalLog_, 0, 3, 4, 3);

        // ============= RIGHT COLUMN ============= //

        // Horizontal
        auto* horizontalFrame = new QGroupBox("Horizontal Configure");
        horizontalFrame->setStyleSheet("QGroupBox::title { color: #C99C0A; }");
        auto* hLayout = new QGridLayout(horizontalFrame);
        rightLayout->addWidget(horizontalFrame);

        auto* lblTdiv = new QLabel("TIME/DIV");
        lblTdiv->setFont(buttonFont_);
        dropTimeDiv_ = new QComboBox();
        dropTimeDiv_->setFont(buttonFont_);
        dropTimeDiv_->addItems({"100 us", "200 us", "500 us", "1 ms", "2 ms", "5 ms", "10 ms"});
        connect(dropTimeDiv_, &QComboBox::currentIndexChanged, this, [this](int) { timeDivideConfigure(); });

        hLayout->addWidget(lblTdiv, 0, 0);
        hLayout->addWidget(dropTimeDiv_, 1, 0, 1, 2);

        // Trigger
        auto* triggerFrame = new QGroupBox("Trigger Configure");
        triggerFrame->setStyleSheet("QGroupBox::title { color: #B9CF0D; }");
        auto* tLayout = new QGridLayout(triggerFrame);
        rightLayout->addWidget(triggerFrame);

        auto* lblTrgSource = new QLabel("SOURCE");
        lblTrgSource->setFont(buttonFont_);
        dropTrigSource_ = new QComboBox();
        dropTrigSource_->setFont(buttonFont_);
        dropTrigSource_->addItems({"CH1", "CH2", "CH3", "CH4", "NONE"});
        connect(dropTrigSource_, &QComboBox::currentIndexChanged, this, [this](int) { changeTriggerSource(); });

        auto* lblTrgSlope = new QLabel("SLOPE");
        lblTrgSlope->setFont(buttonFont_);
        dropTrigSlope_ = new QComboBox();
        dropTrigSlope_->setFont(buttonFont_);
        dropTrigSlope_->addItems({"RISING", "FALLING", "BOTH"});
        connect(dropTrigSlope_, &QComboBox::currentIndexChanged, this, [this](int) { changeTriggerSlope(); });

        auto* lblTrgCoupling = new QLabel("COUPLING");
        lblTrgCoupling->setFont(buttonFont_);
        dropTrigCoup_ = new QComboBox();
        dropTrigCoup_->setFont(buttonFont_);
        dropTrigCoup_->addItems({"AC", "DC", "LFR", "HFR"});
        dropTrigCoup_->setCurrentIndex(1);
        connect(dropTrigCoup_, &QComboBox::currentIndexChanged, this, [this](int) { changeTriggerCoupling(); });

        auto* lblLevelsTrig = new QLabel("TRIGGER LEVEL");
        lblLevelsTrig->setFont(buttonFont_);
        levelTrigInput_ = new QLineEdit("0");
        levelTrigInput_->setFont(buttonFont_);
        auto* btnSendLevelTrg = new QPushButton("APPLY");
        btnSendLevelTrg->setFont(buttonFont_);
        btnSendLevelTrg->setStyleSheet(
            "QPushButton { background-color: #b9c847; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #b9bf8e; }");
        btnSendLevelTrg->setEnabled(false);
        btnSendLevelTrg_ = btnSendLevelTrg;
        connect(btnSendLevelTrg, &QPushButton::clicked, this, [this] { sendLevelTrig(); });

        tLayout->addWidget(lblTrgSource, 0, 0);
        tLayout->addWidget(dropTrigSource_, 1, 0, 1, 2);
        tLayout->addWidget(lblTrgSlope, 0, 3);
        tLayout->addWidget(dropTrigSlope_, 1, 3, 1, 2);
        tLayout->addWidget(lblTrgCoupling, 0, 5);
        tLayout->addWidget(dropTrigCoup_, 1, 5, 1, 2);
        tLayout->addWidget(lblLevelsTrig, 2, 0, 1, 2);
        tLayout->addWidget(levelTrigInput_, 3, 0, 1, 2);
        tLayout->addWidget(btnSendLevelTrg, 3, 2, 1, 2);

        // System Control Frame
        auto* systemFrame = new QGroupBox("Start & Stop / SCPI Commands");
        systemFrame->setStyleSheet("QGroupBox::title { color: #1CC209; }");
        auto* sLayout = new QGridLayout(systemFrame);
        rightLayout->addWidget(systemFrame);

        auto* lblDevicePath = new QLabel("DEVICE");
        lblDevicePath->setFont(buttonFont_);
        devicePathInput_ = new QLineEdit("/dev/usbtmc0");
        devicePathInput_->setFont(buttonFont_);

        btnConnect_ = new QPushButton("CONNECT");
        btnConnect_->setFont(buttonFont_);
        btnConnect_->setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: #ffffff; border: 0; }"
            "QPushButton:hover { background-color: #27ae60; }");
        connect(btnConnect_, &QPushButton::clicked, this, [this] { connectScope(); });

        btnDisconnect_ = new QPushButton("DISCONNECT");
        btnDisconnect_->setFont(buttonFont_);
        btnDisconnect_->setStyleSheet(
            "QPushButton { background-color: #d53f3d; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #c70805; }");
        btnDisconnect_->setEnabled(false);
        connect(btnDisconnect_, &QPushButton::clicked, this, [this] { disconnectScope(); });

        btnSendCmd_ = new QPushButton("SEND COMMANDS");
        btnSendCmd_->setFont(buttonFont_);
        btnSendCmd_->setStyleSheet(
            "QPushButton { background-color: #4594de; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #086ecd; }");
        btnSendCmd_->setEnabled(false);
        connect(btnSendCmd_, &QPushButton::clicked, this, [this] { sendScpiCommand(); });

        ipInput_ = new QLineEdit("*IDN?");
        ipInput_->setFont(buttonFont_);

        txtIdnDisplay_ = new QLineEdit("Scope: Not Connected");
        txtIdnDisplay_->setFont(defaultFont_);
        txtIdnDisplay_->setReadOnly(true);

        btnStart_ = new QPushButton("RUN");
        btnStart_->setFont(buttonFont_);
        btnStart_->setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: #ffffff; border: 0; }"
            "QPushButton:hover { background-color: #27ae60; }");
        btnStart_->setEnabled(false);
        connect(btnStart_, &QPushButton::clicked, this, [this] { scopeRun(); });

        btnStop_ = new QPushButton("STOP");
        btnStop_->setFont(buttonFont_);
        btnStop_->setStyleSheet(
            "QPushButton { background-color: #d53f3d; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #c70805; }");
        btnStop_->setEnabled(false);
        connect(btnStop_, &QPushButton::clicked, this, [this] { scopeStop(); });

        dropTrigMode_ = new QComboBox();
        dropTrigMode_->setFont(buttonFont_);
        dropTrigMode_->addItems({"AUTO", "NORMAL", "SINGLE"});
        connect(dropTrigMode_, &QComboBox::currentIndexChanged, this, [this](int) { changeMode(); });

        btnAutoset_ = new QPushButton("AUTOSET");
        btnAutoset_->setFont(buttonFont_);
        btnAutoset_->setStyleSheet(
            "QPushButton { background-color: #080808; color: #1274e4; border: 0; }"
            "QPushButton:hover { background-color: #000000; color: #044fa4; }");
        btnAutoset_->setEnabled(false);
        connect(btnAutoset_, &QPushButton::clicked, this, [this] { autosetCommand(); });

        btnLogClear_ = new QPushButton("CLEAR LOG MESSAGE");
        btnLogClear_->setFont(buttonFont_);
        btnLogClear_->setStyleSheet(
            "QPushButton { background-color: #32D9C0; color: #000000; border: 0; }"
            "QPushButton:hover { background-color: #8DE0D4; }");
        connect(btnLogClear_, &QPushButton::clicked, this, [this] { terminalLog_->clear(); });

        s_layout_row(sLayout, lblDevicePath, devicePathInput_, btnConnect_, btnDisconnect_);
        sLayout->addWidget(ipInput_, 1, 0, 1, 2);
        sLayout->addWidget(btnSendCmd_, 1, 2, 1, 2);
        sLayout->addWidget(txtIdnDisplay_, 2, 0, 1, 4);
        sLayout->addWidget(btnStart_, 3, 0);
        sLayout->addWidget(btnStop_, 3, 1);
        sLayout->addWidget(dropTrigMode_, 3, 2, 1, 2);
        sLayout->addWidget(btnAutoset_, 4, 0, 1, 2);
        sLayout->addWidget(btnLogClear_, 4, 2, 1, 2);

        rightLayout->addStretch(1);
    }

    // Small helper just to keep buildUi() from becoming an unreadable wall
    // for the device-path / connect / disconnect row.
    void s_layout_row(QGridLayout* layout, QWidget* label, QWidget* input,
                       QWidget* connectBtn, QWidget* disconnectBtn) {
        layout->addWidget(label, 0, 0);
        layout->addWidget(input, 0, 1);
        layout->addWidget(connectBtn, 0, 2);
        layout->addWidget(disconnectBtn, 0, 3);
    }

    // =====================================================================
    // LOGGING
    // =====================================================================
    void logToTerminal(const QString& message) {
        QString timestamp = QDateTime::currentDateTime().toString("HH:mm:ss");
        terminalLog_->append(QString("[%1] %2").arg(timestamp, message));
        terminalLog_->verticalScrollBar()->setValue(terminalLog_->verticalScrollBar()->maximum());
    }

    void logToTerminal(const QString& title, const QString& message) {
        logToTerminal(QString("%1: %2").arg(title, message));
    }

    // Mirrors the "if not self.oscilloscope: log + return" guard used
    // throughout the Python ScopeApp handlers.
    bool ensureConnected() {
        if (!oscilloscope_) {
            logToTerminal("Error", "Oscilloscope is not connected!");
            return false;
        }
        return true;
    }

    // =====================================================================
    // EVENT LOGIC (mirrors ScopeApp's methods in the PyQt6 reference)
    // =====================================================================
    void connectScope() {
        btnConnect_->setText("CONNECTING...");
        btnConnect_->setEnabled(false);
        QApplication::processEvents();

        const std::string path = devicePathInput_->text().trimmed().toStdString();
        try {
            oscilloscope_ = std::make_unique<USBTMCScope>(path);
            QString idn = QString::fromStdString(oscilloscope_->getIdn());

            logToTerminal("Success", QString("Connected to Rigol Scope: %1").arg(idn));
            btnConnect_->setText("CONNECTED");
            btnConnect_->setStyleSheet("QPushButton { background-color: #27ae60; color: #ffffff; border: 0; }");
            btnDisconnect_->setEnabled(true);
            btnSendCmd_->setEnabled(true);
            btnStart_->setEnabled(true);
            btnStop_->setEnabled(true);
            btnAutoset_->setEnabled(true);
            btnInvert_->setEnabled(true);
            btnSendLevelTrg_->setEnabled(true);

            txtIdnDisplay_->setText(QString("Connected: %1").arg(idn));
        } catch (const std::exception& e) {
            logToTerminal("Error", QString("Failed to connect: %1").arg(e.what()));
            btnConnect_->setText("CONNECT");
            btnConnect_->setStyleSheet("QPushButton { background-color: #2ecc71; color: #ffffff; border: 0; }");
            btnConnect_->setEnabled(true);
            oscilloscope_.reset();
            txtIdnDisplay_->setText("Connection Error!");
        }
    }

    void disconnectScope() {
        if (oscilloscope_) {
            oscilloscope_->disconnect();
            oscilloscope_.reset();
        }

        logToTerminal("Disconnected", "Session cleanly terminated.");
        btnConnect_->setText("CONNECT");
        btnConnect_->setStyleSheet("QPushButton { background-color: #2ecc71; color: #ffffff; border: 0; }");
        btnConnect_->setEnabled(true);
        btnDisconnect_->setEnabled(false);
        btnSendCmd_->setEnabled(false);
        btnStart_->setEnabled(false);
        btnStop_->setEnabled(false);
        btnAutoset_->setEnabled(false);
        btnInvert_->setEnabled(false);
        btnSendLevelTrg_->setEnabled(false);
        txtIdnDisplay_->setText("Scope: Not Connected");
    }

    void sendScpiCommand() {
        if (!ensureConnected()) return;

        QString command = ipInput_->text().trimmed();
        if (command.isEmpty()) return;

        try {
            if (command.contains('?')) {
                QString response = QString::fromStdString(oscilloscope_->query(command.toStdString()));
                logToTerminal("Query Response", QString("Sent: %1  Received: %2").arg(command, response));
            } else {
                oscilloscope_->writeCommand(command.toStdString());
                logToTerminal("Command Sent", QString("Successfully wrote: %1").arg(command));
            }
        } catch (const std::exception& e) {
            logToTerminal("Command Error", QString("Execution failed: %1").arg(e.what()));
        }
    }

    void scopeRun() {
        if (!ensureConnected()) return;
        try {
            oscilloscope_->run();
            logToTerminal("Successfully", "Oscilloscope is running now!");
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to send RUN command: %1").arg(e.what()));
        }
    }

    void scopeStop() {
        if (!ensureConnected()) return;
        try {
            oscilloscope_->stop();
            logToTerminal("Successfully", "Oscilloscope is stopping!");
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to send STOP command: %1").arg(e.what()));
        }
    }

    void changeMode() {
        if (!ensureConnected()) return;
        QString mode = dropTrigMode_->currentText();
        try {
            oscilloscope_->setTriggerSweep(mode.toStdString());
            logToTerminal("Successfully", QString("Oscilloscope changed trigger mode into: %1 !").arg(mode));
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to set trigger mode: %1").arg(e.what()));
        }
    }

    void autosetCommand() {
        if (!ensureConnected()) return;
        try {
            oscilloscope_->triggerAutoset();
            logToTerminal("Successfully", "Oscilloscope Autosetting now!");
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to send AUTOSET command: %1").arg(e.what()));
        }
    }

    void changeTriggerSource() {
        if (!ensureConnected()) return;
        QString selected = dropTrigSource_->currentText();
        try {
            if (selected == "NONE") {
                oscilloscope_->setTriggerSource("EXT");
                logToTerminal("Successfully", QString("Oscilloscope changed trigger source into: %1 !").arg(selected));
            } else {
                oscilloscope_->setTriggerSource(selected.toStdString());
                logToTerminal("Successfully", QString("Oscilloscope changed trigger source into: %1 !").arg(selected));
            }
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to set trigger source: %1").arg(e.what()));
        }
    }

    void changeTriggerSlope() {
        if (!ensureConnected()) return;
        QString selected = dropTrigSlope_->currentText();
        try {
            oscilloscope_->setTriggerSlope(selected.toStdString());
            logToTerminal("Successfully", QString("Oscilloscope sets the edge trigger into: %1 !").arg(selected));
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to set trigger slope: %1").arg(e.what()));
        }
    }

    void changeTriggerCoupling() {
        if (!ensureConnected()) return;
        QString selected = dropTrigCoup_->currentText();
        try {
            oscilloscope_->setTriggerCoupling(selected.toStdString());
            logToTerminal("Successfully", QString("Oscilloscope set the trigger coupling into: %1 !").arg(selected));
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to set trigger coupling: %1").arg(e.what()));
        }
    }

    void changeVoltDiv() {
        if (!ensureConnected()) return;

        static const std::map<QString, double> voltMap = {
            {"100 mV", 0.1}, {"200 mV", 0.2}, {"500 mV", 0.5},
            {"1 V", 1.0}, {"2 V", 2.0}, {"10 V", 10.0}
        };
        QString selected = voltDiv_->currentText();
        double value = voltMap.count(selected) ? voltMap.at(selected) : 1.0;

        try {
            oscilloscope_->voltageScale(activeChannel_, value);
            logToTerminal("Successfully",
                QString("Oscilloscope Channel%1 vertical scale sets into: %2 !").arg(activeChannel_).arg(value));
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to set vertical scale: %1").arg(e.what()));
        }
    }

    void changeCoupling() {
        if (!ensureConnected()) return;
        QString selected = coupChannel_->currentText();
        try {
            oscilloscope_->configureCoupling(activeChannel_, selected.toStdString());
            logToTerminal("Successfully",
                QString("Oscilloscope Channel%1 coupling mode set into: %2 !").arg(activeChannel_).arg(selected));
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to set coupling: %1").arg(e.what()));
        }
    }

    void invertSignal() {
        if (!ensureConnected()) return;
        try {
            oscilloscope_->toggleInvert(activeChannel_);
            logToTerminal("Successfully", QString("Oscilloscope Channel%1 inverted!").arg(activeChannel_));
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to toggle invert: %1").arg(e.what()));
        }
    }

    void timeDivideConfigure() {
        if (!ensureConnected()) return;

        static const std::map<QString, double> timeMap = {
            {"100 us", 0.0001}, {"200 us", 0.0002}, {"500 us", 0.0005},
            {"1 ms", 0.001}, {"2 ms", 0.002}, {"5 ms", 0.005}, {"10 ms", 0.010}
        };
        QString selected = dropTimeDiv_->currentText();
        double value = timeMap.count(selected) ? timeMap.at(selected) : 0.001;

        try {
            oscilloscope_->timeScale(value);
            logToTerminal("Successfully", QString("Oscilloscope horizontal scale sets into: %1 !").arg(value));
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to set horizontal scale: %1").arg(e.what()));
        }
    }

    void probeSetting() {
        if (!ensureConnected()) return;

        static const std::map<QString, QString> probeMap = {
            {"X0.1", "0.1"}, {"X0.2", "0.2"}, {"X0.5", "0.5"}, {"X1", "1"},
            {"X2", "2"}, {"X5", "5"}, {"X10", "10"}
        };
        QString selected = probeConfigChannel_->currentText();
        QString attenuation = probeMap.count(selected) ? probeMap.at(selected) : "1";

        try {
            oscilloscope_->configureProbe(activeChannel_, attenuation.toStdString());
            logToTerminal("Successfully",
                QString("Oscilloscope Channel%1 probe sets into: %2 !").arg(activeChannel_).arg(selected));
        } catch (const std::exception& e) {
            logToTerminal("SCPI Error", QString("Failed to set probe attenuation: %1").arg(e.what()));
        }
    }

    void sendLevelTrig() {
        if (!ensureConnected()) return;

        QString levelText = levelTrigInput_->text().trimmed();
        if (levelText.isEmpty()) return;

        bool ok = false;
        double level = levelText.toDouble(&ok);
        if (!ok) {
            logToTerminal("Command Error", QString("'%1' is not a valid number.").arg(levelText));
            return;
        }

        try {
            oscilloscope_->triggerLevel(level);
            logToTerminal("Successfully", QString("Oscilloscope trigger level changed: %1 !").arg(levelText));
        } catch (const std::exception& e) {
            logToTerminal("Command Error", QString("Execution failed: %1").arg(e.what()));
        }
    }

    // =====================================================================
    // STATE
    // =====================================================================
    std::unique_ptr<USBTMCScope> oscilloscope_;
    int activeChannel_ = 1;

    QFont channelFont_, defaultFont_, buttonFont_;

    QTextEdit* terminalLog_ = nullptr;

    QComboBox* voltDiv_ = nullptr;
    QComboBox* coupChannel_ = nullptr;
    QComboBox* probeConfigChannel_ = nullptr;
    QRadioButton *radCh1_, *radCh2_, *radCh3_, *radCh4_;
    QButtonGroup* channelGroup_ = nullptr;
    QPushButton* btnInvert_ = nullptr;

    QComboBox* dropTimeDiv_ = nullptr;
    QComboBox* dropTrigSource_ = nullptr;
    QComboBox* dropTrigSlope_ = nullptr;
    QComboBox* dropTrigCoup_ = nullptr;
    QLineEdit* levelTrigInput_ = nullptr;
    QPushButton* btnSendLevelTrg_ = nullptr;

    QLineEdit* devicePathInput_ = nullptr;
    QPushButton* btnConnect_ = nullptr;
    QPushButton* btnDisconnect_ = nullptr;
    QPushButton* btnSendCmd_ = nullptr;
    QLineEdit* ipInput_ = nullptr;
    QLineEdit* txtIdnDisplay_ = nullptr;
    QPushButton* btnStart_ = nullptr;
    QPushButton* btnStop_ = nullptr;
    QComboBox* dropTrigMode_ = nullptr;
    QPushButton* btnAutoset_ = nullptr;
    QPushButton* btnLogClear_ = nullptr;
};

int main(int argc, char* argv[]) {
    QApplication app(argc, argv);
    RigolScopeApp window;
    window.show();
    return app.exec();
}

#include "RigolDisplay.moc"
