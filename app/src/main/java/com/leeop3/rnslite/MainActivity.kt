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
        val btnPicker = Button(this).apply { text = "1. Select RNode" }
        val btnStart = Button(this).apply { text = "2. Start RNS" }
        val txtStatus = TextView(this).apply { text = "Status: Disconnected"; setPadding(0,10,0,10) }
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
            if (devices.isEmpty()) {
                Toast.makeText(this, "Pair RNode in System Settings first", Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }
            val names = devices.map { "${it.first} (${it.second})" }.toTypedArray()
            AlertDialog.Builder(this).setTitle("Select RNode").setItems(names) { _, i ->
                selectedMac = devices[i].second
                txtStatus.text = "Selected: ${devices[i].first}"
            }.show()
        }

        btnStart.setOnClickListener {
            val mac = selectedMac ?: return@setOnClickListener Toast.makeText(this, "Select device first", Toast.LENGTH_SHORT).show()
            lifecycleScope.launch {
                txtStatus.text = "Connecting BT..."
                if (btService.connect(mac)) {
                    val addr = RNSBridge.start(this@MainActivity, btService)
                    txtStatus.text = "RNS Online: $addr"
                    isRnsStarted = true
                    Toast.makeText(this@MainActivity, "Connected!", Toast.LENGTH_SHORT).show()
                } else {
                    txtStatus.text = "BT Failed. Re-pair device?"
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
                    val msgs = RNSBridge.fetchInbox()
                    for (m in msgs) txtInbox.append("${m["sender"]}: ${m["content"]}\n")
                }
            }
        }

        val perms = mutableListOf(
            android.Manifest.permission.BLUETOOTH_CONNECT,
            android.Manifest.permission.BLUETOOTH_SCAN,
            android.Manifest.permission.ACCESS_FINE_LOCATION
        )
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            perms.add("android.permission.POST_NOTIFICATIONS")
        }
        requestPermissions(perms.toTypedArray(), 1)
    }
}