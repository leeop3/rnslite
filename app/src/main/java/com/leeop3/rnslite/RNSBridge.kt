package com.leeop3.rnslite
import com.chaquo.python.Python
import android.content.Context

object RNSBridge {
    private fun getWorker() = Python.getInstance().getModule("rns_worker")

    fun startWithContext(context: Context, bt: BluetoothService, name: String): String {
        val path = context.filesDir.absolutePath + "/.reticulum"
        return getWorker().callAttr("start", path, bt, name).toString()
    }

    fun sendText(dest: String, text: String): String {
        return getWorker().callAttr("send_lxm", dest, text).toString()
    }

    fun getUpdates(): Map<String, Any> {
        val pyMap = getWorker().callAttr("get_updates").asMap()
        val result = mutableMapOf<String, Any>()
        
        val inboxRaw = pyMap[Python.getBuiltins().get("str").call("inbox")]?.asList()
        result["inbox"] = inboxRaw?.map { it.asMap().entries.associate { (k, v) -> k.toString() to v.toString() } } ?: emptyList<Map<String, String>>()
        
        val nodesRaw = pyMap[Python.getBuiltins().get("str").call("nodes")]?.asList()
        result["nodes"] = nodesRaw?.map { it.toString() } ?: emptyList<String>()
        
        return result
    }
}