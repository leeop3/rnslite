package com.leeop3.rnslite
import com.chaquo.python.Python
import android.content.Context

object RNSBridge {
    private fun getWorker() = Python.getInstance().getModule("rns_worker")

    fun start(bt: BluetoothService): String {
        return getWorker().callAttr("start", bt).toString()
    }

    fun sendText(dest: String, text: String): String {
        return getWorker().callAttr("send_text", dest, text).toString()
    }

    fun getUpdates(): Map<String, Any> {
        val pyData = getWorker().callAttr("get_updates").asMap()
        val result = mutableMapOf<String, Any>()
        
        val inbox = pyData.get("inbox")?.asList()?.map { item ->
            val m = item.asMap()
            m.entries.associate { it.key.toString() to it.value.toString() }
        } ?: emptyList<Map<String, String>>()
        
        val nodes = pyData.get("nodes")?.asList()?.map { it.toString() } ?: emptyList<String>()
        
        result["inbox"] = inbox
        result["nodes"] = nodes
        return result
    }
}