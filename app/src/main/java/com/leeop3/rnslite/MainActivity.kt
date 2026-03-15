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
    private var myHash: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))

        val scroller = ScrollView(this)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(30,30,30,30) }
        
        val etName = EditText(this).apply { hint = "Display Name" }
        val btnPicker = Button(this).apply { text = "Select RNode" }
        val btnStart = Button(this).apply { text = "Go Online" }
        val txtStatus = TextView(this).apply { text = "Status: Offline"; setPadding(0,10,0,10) }
        val txtNodes = TextView(this).apply { text = "Nearby:\n--"; textSize = 12f }
        val etDest = EditText(this).apply { hint = "Target Hash" }
        val etMsg = EditText(this).apply { hint = "Message" }
        val btnSend = Button(this).apply { text = "Send Text" }
        val btnImg = Button(this).apply { text = "Send Test Image" }
        val txtInbox = TextView(this).apply { text = "Inbox:\n"; setPadding(0,20,0,0) }

        layout.addView(etName); layout.addView(btnPicker); layout.addView(btnStart); layout.addView(txtStatus)
        layout.addView(txtNodes); layout.addView(etDest); layout.addView(etMsg); layout.addView(btnSend); layout.addView(btnImg); layout.addView(txtInbox)
        scroller.addView(layout); setContentView(scroller)

        var selectedMac: String? = null
        btnPicker.setOnClickListener {
            val devices = btService.getPairedDevices()
            val names = devices.map { it.first }.toTypedArray()
            AlertDialog.Builder(this).setTitle("Select RNode").setItems(names) { _, i ->
                selectedMac = devices[i].second
                txtStatus.text = "Selected: ${devices[i].first}"
            }.show()
        }

        btnStart.setOnClickListener {
            val mac = selectedMac ?: return@setOnClickListener
            val name = if(etName.text.isEmpty()) "LiteNode" else etName.text.toString()
            lifecycleScope.launch {
                if (btService.connect(mac)) {
                    myHash = RNSBridge.startWithContext(this@MainActivity, btService, name)
                    txtStatus.text = "Online: $myHash"
                }
            }
        }

        btnSend.setOnClickListener {
            if (myHash == null) return@setOnClickListener
            val res = RNSBridge.sendText(etDest.text.toString(), etMsg.text.toString())
            Toast.makeText(this, res, Toast.LENGTH_SHORT).show()
        }

        btnImg.setOnClickListener {
            if (myHash == null) return@setOnClickListener
            // Sending a tiny 1x1 base64 pixel as a test
            val dummy = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
            val res = RNSBridge.sendImage(etDest.text.toString(), dummy)
            Toast.makeText(this, res, Toast.LENGTH_SHORT).show()
        }

        lifecycleScope.launch {
            while(true) {
                delay(4000)
                if (myHash != null) {
                    try {
                        val updates = RNSBridge.getUpdates()
                        val msgs = updates["inbox"] as? List<Map<String, String>>
                        val nodes = updates["nodes"] as? List<String>
                        msgs?.forEach { m -> txtInbox.append("${m["sender"]}: ${m["content"]}\n") }
                        if (!nodes.isNullOrEmpty()) txtNodes.text = "Nearby:\n" + nodes.joinToString("\n")
                    } catch(e: Exception) { }
                }
            }
        }
        requestPermissions(arrayOf(android.Manifest.permission.BLUETOOTH_CONNECT, android.Manifest.permission.BLUETOOTH_SCAN, android.Manifest.permission.ACCESS_FINE_LOCATION), 1)
    }
}