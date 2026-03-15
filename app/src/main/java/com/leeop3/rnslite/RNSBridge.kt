package com.leeop3.rnslite
import com.chaquo.python.Python
import android.content.Context

object RNSBridge {
    private fun getWorker() = Python.getInstance().getModule("rns_worker")

    fun startWithContext(context: Context, bt: BluetoothService, name: String): String {
        val storagePath = context.filesDir.absolutePath
        // PASSING 3 ARGUMENTS: path, bt, and name
        return getWorker().callAttr("start", storagePath, bt, name).toString()
    }

    fun sendText(dest: String, text: String): String {
        return getWorker().callAttr("send_text", dest, text).toString()
    }

    fun getUpdates(): Map<String, Any> {
        val pyData = getWorker().callAttr("get_updates")
        val result = mutableMapOf<String, Any>()
        
        val inboxRaw = pyData.get("inbox")?.asList()
        val inboxList = mutableListOf<Map<String, String>>()
        inboxRaw?.forEach { item ->
            val entry = mutableMapOf<String, String>()
            val itemMap = item.asMap()
            for (key in itemMap.keys) {
                entry[key.toString()] = itemMap.get(key).toString()
            }
            inboxList.add(entry)
        }
        result["inbox"] = inboxList
        
        val nodesRaw = pyData.get("nodes")?.asList()
        val nodesList = mutableListOf<String>()
        nodesRaw?.forEach { nodesList.add(it.toString()) }
        result["nodes"] = nodesList
        
        val logsRaw = pyData.get("logs")?.asList()
        val logsList = mutableListOf<String>()
        logsRaw?.forEach { logsList.add(it.toString()) }
        result["logs"] = logsList
        
        return result
    }
}