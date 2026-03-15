package com.leeop3.rnslite
import com.chaquo.python.Python
import android.content.Context

object RNSBridge {
    private fun getWorker() = Python.getInstance().getModule("rns_worker")

    fun start(context: Context, btService: BluetoothService): String {
        // Get the internal files directory from Android
        val storagePath = context.filesDir.absolutePath + "/.reticulum"
        return getWorker().callAttr("start", storagePath, btService).toString()
    }

    fun sendText(dest: String, text: String): String {
        return getWorker().callAttr("send_txt", dest, text).toString()
    }

    fun fetchInbox(): List<Map<String, String>> {
        val raw = getWorker().callAttr("get_inbox").asList()
        return raw.map { it.asMap().entries.associate { (k, v) -> k.toString() to v.toString() } }
    }
}