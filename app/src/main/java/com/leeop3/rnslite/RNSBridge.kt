package com.leeop3.rnslite
import com.chaquo.python.Python
import com.chaquo.python.PyObject
import android.content.Context

object RNSBridge {
    private fun getWorker() = Python.getInstance().getModule("rns_worker")

    fun startWithContext(context: Context, bt: BluetoothService, name: String): String {
        val path = context.filesDir.absolutePath + "/.reticulum"
        return getWorker().callAttr("start", path, bt, name).toString()
    }

    fun sendText(dest: String, text: String): String {
        return getWorker().callAttr("send_text", dest, text).toString()
    }

    fun getUpdates(): Map<String, Any> {
        val pyUpdates = getWorker().callAttr("get_updates")
        val result = mutableMapOf<String, Any>()
        
        val inboxList = mutableListOf<Map<String, String>>()
        pyUpdates.get("inbox")?.asList()?.forEach { item ->
            val entry = mutableMapOf<String, String>()
            val itemMap = item.asMap()
            for (key in itemMap.keys) { entry[key.toString()] = itemMap.get(key).toString() }
            inboxList.add(entry)
        }
        result["inbox"] = inboxList
        
        val nodesList = pyUpdates.get("nodes")?.asList()?.map { it.toString() } ?: emptyList<String>()
        result["nodes"] = nodesList

        val logsList = pyUpdates.get("logs")?.asList()?.map { it.toString() } ?: emptyList<String>()
        result["logs"] = logsList
        
        return result
    }
}