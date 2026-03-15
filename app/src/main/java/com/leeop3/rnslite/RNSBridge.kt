package com.leeop3.rnslite
import com.chaquo.python.Python
import com.chaquo.python.PyObject
import android.content.Context

object RNSBridge {
    private fun getWorker() = Python.getInstance().getModule("rns_worker")

    fun startWithContext(context: Context, bt: BluetoothService, name: String): String {
        return getWorker().callAttr("start", context.filesDir.absolutePath, bt, name).toString()
    }

    fun sendText(dest: String, text: String): String {
        return getWorker().callAttr("send_text", dest, text).toString()
    }

    fun getUpdates(): Map<String, List<String>> {
        val updatesObj = getWorker().callAttr("get_updates")
        val result = mutableMapOf<String, List<String>>()
        
        // Use direct PyObject.get() to avoid Kotlin generic inference bugs
        val inboxRaw = updatesObj.get("inbox")?.asList()
        result["inbox"] = inboxRaw?.map { it.toString() } ?: emptyList()
        
        val nodesRaw = updatesObj.get("nodes")?.asList()
        result["nodes"] = nodesRaw?.map { it.toString() } ?: emptyList()
        
        return result
    }
}