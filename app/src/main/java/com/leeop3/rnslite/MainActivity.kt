package com.leeop3.rnslite
import android.os.Bundle
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(50, 50, 50, 50)
        }
        val etDest = EditText(this).apply { hint = "Destination Hash" }
        val etMsg = EditText(this).apply { hint = "Message" }
        val btnSend = Button(this).apply { text = "Send via LXMF" }
        
        layout.addView(etDest); layout.addView(etMsg); layout.addView(btnSend)
        setContentView(layout)

        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
        val py = Python.getInstance().getModule("rns_backend")
        py.callAttr("initialize", filesDir.absolutePath)

        btnSend.setOnClickListener {
            val res = py.callAttr("send_msg", etDest.text.toString(), etMsg.text.toString()).toString()
            Toast.makeText(this, res, Toast.LENGTH_SHORT).show()
        }
    }
}
