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
        val pyUpdates = getWorker().callAttr("get_updates").asMap()
        val result = mutableMapOf<String, Any>()
        
        // Safely extract Inbox
        val inboxList = mutableListOf<Map<String, String>>()
        val pyInbox = pyUpdates["inbox"]?.asList()
        pyInbox?.forEach { item ->
            val m = item.asMap()
            val entry = mutableMapOf<String, String>()
            m.forEach { (k, v) -> entry[k.toString()] = v.toString() }
            inboxList.add(entry)
        }
        result["inbox"] = inboxList
        
        // Safely extract Nodes
        val nodesList = mutableListOf<String>()
        val pyNodes = pyUpdates["nodes"]?.asList()
        pyNodes?.forEach { nodesList.add(it.toString()) }
        result["nodes"] = nodesList
        
        return result
    }
}