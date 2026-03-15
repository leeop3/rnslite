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
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))

        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(40,40,40,40) }
        val btnPicker = Button(this).apply { text = "1. Select Paired RNode" }
        val btnStart = Button(this).apply { text = "2. Start RNS" }
        val txtStatus = TextView(this).apply { text = "Status: Disconnected" }
        val etDest = EditText(this).apply { hint = "Recipient Hash" }
        val etMsg = EditText(this).apply { hint = "Message" }
        val btnSend = Button(this).apply { text = "Send" }
        val txtInbox = TextView(this).apply { text = "Inbox:\n" }

        layout.addView(btnPicker); layout.addView(btnStart); layout.addView(txtStatus)
        layout.addView(etDest); layout.addView(etMsg); layout.addView(btnSend); layout.addView(txtInbox)
        setContentView(layout)

        var selectedMac: String? = null

        btnPicker.setOnClickListener {
            val devices = btService.getPairedDevices()
            val names = devices.map { "${it.first} (${it.second})" }.toTypedArray()
            AlertDialog.Builder(this).setTitle("Select RNode").setItems(names) { _, i ->
                selectedMac = devices[i].second
                txtStatus.text = "Selected: ${devices[i].first}"
            }.show()
        }

        btnStart.setOnClickListener {
            val mac = selectedMac ?: return@setOnClickListener
            lifecycleScope.launch {
                txtStatus.text = "Connecting..."
                if (btService.connect(mac)) {
                    // Added "this" as context
                    val addr = RNSBridge.start(this@MainActivity, btService)
                    txtStatus.text = "RNS Online: $addr"
                    isRnsStarted = true
                }
            }
        }

        btnSend.setOnClickListener {
            if (!isRnsStarted) return@setOnClickListener
            val res = RNSBridge.sendText(etDest.text.toString(), etMsg.text.toString())
            Toast.makeText(this, res, Toast.LENGTH_SHORT).show()
        }

        lifecycleScope.launch {
            while(true) {
                delay(3000)
                if (isRnsStarted) {
                    try {
                        val msgs = RNSBridge.fetchInbox()
                        for (m in msgs) txtInbox.append("${m["sender"]}: ${m["content"]}\n")
                    } catch(e: Exception) {}
                }
            }
        }

        requestPermissions(arrayOf(android.Manifest.permission.BLUETOOTH_CONNECT, android.Manifest.permission.BLUETOOTH_SCAN, android.Manifest.permission.ACCESS_FINE_LOCATION), 1)
    }
}