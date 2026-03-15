package com.leeop3.rnslite
import android.os.Bundle
import android.widget.*
import android.graphics.Color
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
        
        val btnPicker = Button(this).apply { text = "1. Select RNode" }
        val btnStart = Button(this).apply { text = "2. Go Online" }
        val txtStatus = TextView(this).apply { text = "Status: Offline"; setPadding(0,10,0,10) }
        val txtNodes = TextView(this).apply { text = "Nearby:\n--"; textSize = 12f; setTextColor(Color.BLUE) }
        val etDest = EditText(this).apply { hint = "Target Hash" }
        val etMsg = EditText(this).apply { hint = "Message" }
        val btnSend = Button(this).apply { text = "Send Message" }
        val txtInbox = TextView(this).apply { text = "Inbox:\n" }
        
        val txtLogs = TextView(this).apply { 
            text = "--- System Logs ---\n"
            textSize = 10f
            setBackgroundColor(Color.LTGRAY)
            setTextColor(Color.BLACK)
        }

        layout.addView(btnPicker); layout.addView(btnStart); layout.addView(txtStatus)
        layout.addView(txtNodes); layout.addView(etDest); layout.addView(etMsg); layout.addView(btnSend)
        layout.addView(txtInbox); layout.addView(txtLogs)
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
            lifecycleScope.launch {
                if (btService.connect(mac)) {
                    myHash = RNSBridge.startWithContext(this@MainActivity, btService, "LiteNode")
                    txtStatus.text = "Online: $myHash"
                }
            }
        }

        btnSend.setOnClickListener {
            if (myHash == null) return@setOnClickListener
            val res = RNSBridge.sendText(etDest.text.toString(), etMsg.text.toString())
            Toast.makeText(this, res, Toast.LENGTH_LONG).show()
        }

        lifecycleScope.launch {
            while(true) {
                delay(3000)
                if (myHash != null) {
                    try {
                        val updates = RNSBridge.getUpdates()
                        val msgs = updates["inbox"] as? List<Map<String, String>>
                        val nodes = updates["nodes"] as? List<String>
                        val logs = updates["logs"] as? List<String>
                        
                        msgs?.forEach { m -> txtInbox.append("${m["sender"]}: ${m["content"]}\n") }
                        logs?.forEach { l -> txtLogs.append("$l\n") }
                        if (!nodes.isNullOrEmpty()) txtNodes.text = "Nearby:\n" + nodes.joinToString("\n")
                    } catch(e: Exception) { }
                }
            }
        }
        requestPermissions(arrayOf(android.Manifest.permission.BLUETOOTH_CONNECT, android.Manifest.permission.BLUETOOTH_SCAN, android.Manifest.permission.ACCESS_FINE_LOCATION), 1)
    }
}