package com.leeop3.rnslite
import android.os.Bundle
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.chaquo.python.android.AndroidPlatform
import com.chaquo.python.Python
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private val btService = BluetoothService()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Request Permissions for Android 12+
        requestPermissions(arrayOf(android.Manifest.permission.BLUETOOTH_CONNECT, android.Manifest.permission.ACCESS_FINE_LOCATION), 1)

        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(50,50,50,50) }
        val etMac = EditText(this).apply { hint = "RNode MAC (e.g. 00:11:22:33:44:55)" }
        val btnConn = Button(this).apply { text = "Connect RNode" }
        val btnSend = Button(this).apply { text = "Send Test Message" }
        
        layout.addView(etMac); layout.addView(btnConn); layout.addView(btnSend)
        setContentView(layout)

        if (!Python.isStarted()) Python.start(AndroidPlatform(this))

        btnConn.setOnClickListener {
            lifecycleScope.launch {
                val success = btService.connect(etMac.text.toString())
                if (success) {
                    val status = RNSBridge.start(btService)
                    Toast.makeText(this@MainActivity, status, Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this@MainActivity, "Connection Failed", Toast.LENGTH_SHORT).show()
                }
            }
        }

        btnSend.setOnClickListener {
            val res = RNSBridge.sendMessage("bb4306cfc7247657962b9f8992451f2b", "Hello via BT!")
            Toast.makeText(this, res, Toast.LENGTH_SHORT).show()
        }
    }
}