package com.leeop3.rnslite
import com.chaquo.python.Python

object RNSBridge {
    private val py = Python.getInstance().getModule("rns_worker")

    fun start(btService: BluetoothService): String {
        val wrapper = Python.getInstance().getModule("bt_wrapper").callAttr("BtWrapper", btService)
        return py.callAttr("start", wrapper).toString()
    }

    fun sendText(dest: String, text: String): String {
        return py.callAttr("send_txt", dest, text).toString()
    }

    fun sendImage(dest: String, base64Image: String): String {
        return py.callAttr("send_img", dest, base64Image).toString()
    }

    fun fetchInbox(): List<Map<String, String>> {
        val raw = py.callAttr("get_inbox").asList()
        return raw.map { it.asMap().entries.associate { (k, v) -> k.toString() to v.toString() } }
    }
}