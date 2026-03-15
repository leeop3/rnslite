package com.leeop3.rnslite
import com.chaquo.python.Python

object RNSBridge {
    // This now waits until the first time it is actually needed
    private fun getWorker() = Python.getInstance().getModule("rns_worker")

    fun start(btService: BluetoothService): String {
        val py = Python.getInstance()
        val wrapper = py.getModule("bt_wrapper").callAttr("BtWrapper", btService)
        return getWorker().callAttr("start", wrapper).toString()
    }

    fun sendText(dest: String, text: String): String {
        return getWorker().callAttr("send_txt", dest, text).toString()
    }

    fun fetchInbox(): List<Map<String, String>> {
        val raw = getWorker().callAttr("get_inbox").asList()
        return raw.map { it.asMap().entries.associate { (k, v) -> k.toString() to v.toString() } }
    }
}