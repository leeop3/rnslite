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
    private var isRnsStarted = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 1. Initialize Python immediately
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // UI Setup
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
            AlertDialog.Builder(this).setTitle("Select RNode").setItems(names) { _, which ->
                selectedMac = devices[which].second
                txtStatus.text = "Selected: ${devices[which].first}"
            }.show()
        }

        btnStart.setOnClickListener {
            val mac = selectedMac ?: return@setOnClickListener Toast.makeText(this, "Select device", Toast.LENGTH_SHORT).show()
            lifecycleScope.launch {
                txtStatus.text = "Connecting BT..."
                if (btService.connect(mac)) {
                    val addr = RNSBridge.start(btService)
                    txtStatus.text = "RNS Online: $addr"
                    isRnsStarted = true
                } else {
                    txtStatus.text = "BT Connection Failed"
                }
            }
        }

        btnSend.setOnClickListener {
            if (!isRnsStarted) return@setOnClickListener Toast.makeText(this, "Start RNS first", Toast.LENGTH_SHORT).show()
            val res = RNSBridge.sendText(etDest.text.toString(), etMsg.text.toString())
            Toast.makeText(this, res, Toast.LENGTH_SHORT).show()
        }

        // Inbox Loop: only runs if RNS is started
        lifecycleScope.launch {
            while(true) {
                delay(3000)
                if (isRnsStarted) {
                    try {
                        val newMsgs = RNSBridge.fetchInbox()
                        for (m in newMsgs) {
                            txtInbox.append("${m["sender"]}: ${m["content"]}\n")
                        }
                    } catch(e: Exception) { }
                }
            }
        }
        
        requestPermissions(arrayOf(android.Manifest.permission.BLUETOOTH_CONNECT, android.Manifest.permission.ACCESS_FINE_LOCATION), 1)
    }
}