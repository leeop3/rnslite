package com.leeop3.rnslite
import com.chaquo.python.Python

object RNSBridge {
    fun start(btService: BluetoothService): String {
        val py = Python.getInstance()
        val pyBtWrapper = py.getModule("bt_wrapper").callAttr("BtWrapper", btService)
        return py.getModule("rns_worker").callAttr("start", pyBtWrapper).toString()
    }

    fun sendMessage(dest: String, text: String): String {
        return Python.getInstance().getModule("rns_worker").callAttr("send_message", dest, text).toString()
    }
}