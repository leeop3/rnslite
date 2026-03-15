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
        val pyUpdatesObj = getWorker().callAttr("get_updates")
        val pyMap = pyUpdatesObj.asMap()
        val result = mutableMapOf<String, Any>()
        
        // Extract Inbox - Explicitly handling types
        val inboxList = mutableListOf<Map<String, String>>()
        val inboxObj = pyMap.get("inbox") as? PyObject
        inboxObj?.asList()?.forEach { item ->
            val m = item.asMap()
            val entry = mutableMapOf<String, String>()
            m.forEach { (k, v) -> entry[k.toString()] = v.toString() }
            inboxList.add(entry)
        }
        result["inbox"] = inboxList
        
        // Extract Nodes - Explicitly handling types
        val nodesList = mutableListOf<String>()
        val nodesObj = pyMap.get("nodes") as? PyObject
        nodesObj?.asList()?.forEach { 
            nodesList.add(it.toString())
        }
        result["nodes"] = nodesList
        
        return result
    }
}