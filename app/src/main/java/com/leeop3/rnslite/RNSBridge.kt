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
        return getWorker().callAttr("send_lxm", dest, text).toString()
    }

    fun getUpdates(): Map<String, Any> {
        val pyUpdates = getWorker().callAttr("get_updates")
        val result = mutableMapOf<String, Any>()
        
        // Extract Inbox - Direct Python dictionary access
        val inboxList = mutableListOf<Map<String, String>>()
        val pyInbox = pyUpdates.get("inbox")?.asList()
        pyInbox?.forEach { item ->
            val entry = mutableMapOf<String, String>()
            val pyItemMap = item.asMap()
            // Iterate over the keys manually to avoid generic inference issues
            for (key in pyItemMap.keys) {
                val k = key.toString()
                val v = pyItemMap.get(key)?.toString() ?: ""
                entry[k] = v
            }
            inboxList.add(entry)
        }
        result["inbox"] = inboxList
        
        // Extract Nodes - Direct Python dictionary access
        val nodesList = mutableListOf<String>()
        val pyNodes = pyUpdates.get("nodes")?.asList()
        pyNodes?.forEach { 
            nodesList.add(it.toString())
        }
        result["nodes"] = nodesList
        
        return result
    }
}