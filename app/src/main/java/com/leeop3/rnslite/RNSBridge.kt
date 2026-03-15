package com.leeop3.rnslite
import com.chaquo.python.Python

object RNSBridge {
    private fun getWorker() = Python.getInstance().getModule("rns_worker")

    fun start(btService: BluetoothService): String {
        // We pass the btService directly to the Python start function
        return getWorker().callAttr("start", null, btService).toString()
    }

    fun sendText(dest: String, text: String): String {
        return getWorker().callAttr("send_txt", dest, text).toString()
    }

    fun fetchInbox(): List<Map<String, String>> {
        val raw = getWorker().callAttr("get_inbox").asList()
        return raw.map { it.asMap().entries.associate { (k, v) -> k.toString() to v.toString() } }
    }
}