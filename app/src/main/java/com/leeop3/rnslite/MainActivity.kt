package com.leeop3.rnslite
import android.os.Bundle
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.chaquo.python.android.AndroidPlatform
import com.chaquo.python.Python
import kotlinx.coroutines.*

class MainActivity : AppCompatActivity() {
    private val btService = BluetoothService()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Setup UI
        val layout = LinearLayout(this).apply { 
            orientation = LinearLayout.VERTICAL
            setPadding(40,40,40,40) 
        }
        val btnPicker = Button(this).apply { text = "1. Select Paired RNode" }
        val btnStart = Button(this).apply { text = "2. Start RNS" }
        val txtStatus = TextView(this).apply { text = "Status: Disconnected"; setPadding(0,20,0,20) }
        val etDest = EditText(this).apply { hint = "Recipient Hash" }
        val etMsg = EditText(this).apply { hint = "Message Text" }
        val btnSend = Button(this).apply { text = "Send Message" }
        val txtInbox = TextView(this).apply { text = "Inbox:\n" }

        layout.addView(btnPicker); layout.addView(btnStart); layout.addView(txtStatus)
        layout.addView(etDest); layout.addView(etMsg); layout.addView(btnSend); layout.addView(txtInbox)
        setContentView(layout)

        var selectedMac: String? = null

        btnPicker.setOnClickListener {
            val devices = btService.getPairedDevices()
            if (devices.isEmpty()) {
                Toast.makeText(this, "No paired devices found", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val names = devices.map { "${it.first} (${it.second})" }.toTypedArray()
            AlertDialog.Builder(this)
                .setTitle("Select RNode")
                .setItems(names) { _, which ->
                    selectedMac = devices[which].second
                    txtStatus.text = "Selected: ${devices[which].first}"
                    Toast.makeText(this, "Ready to connect", Toast.LENGTH_SHORT).show()
                }
                .show()
        }

        btnStart.setOnClickListener {
            val mac = selectedMac
            if (mac == null) {
                Toast.makeText(this, "Please select a device first", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            lifecycleScope.launch {
                txtStatus.text = "Connecting..."
                if (btService.connect(mac)) {
                    if (!Python.isStarted()) Python.start(AndroidPlatform(this@MainActivity))
                    val addr = RNSBridge.start(btService)
                    txtStatus.text = "RNS Online: $addr"
                } else {
                    txtStatus.text = "Connection Failed"
                }
            }
        }

        btnSend.setOnClickListener {
            val res = RNSBridge.sendText(etDest.text.toString(), etMsg.text.toString())
            Toast.makeText(this, res, Toast.LENGTH_SHORT).show()
        }

        // Inbox Refresh Loop
        lifecycleScope.launch {
            while(true) {
                delay(3000)
                try {
                    val newMsgs = RNSBridge.fetchInbox()
                    for (m in newMsgs) {
                        txtInbox.append("${m["sender"]}: ${m["content"]}\n")
                    }
                } catch(e: Exception) {}
            }
        }
        
        // Final permission check for Android 12+
        requestPermissions(arrayOf(
            android.Manifest.permission.BLUETOOTH_CONNECT,
            android.Manifest.permission.BLUETOOTH_SCAN,
            android.Manifest.permission.ACCESS_FINE_LOCATION
        ), 1)
    }
}