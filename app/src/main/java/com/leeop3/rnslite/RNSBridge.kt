package com.leeop3.rnslite
import com.chaquo.python.Python
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
        val pyData = getWorker().callAttr("get_updates").asMap()
        val result = mutableMapOf<String, List<String>>()
        result["inbox"] = pyData.get("inbox")?.asList()?.map { it.toString() } ?: emptyList()
        result["nodes"] = pyData.get("nodes")?.asList()?.map { it.toString() } ?: emptyList()
        return result
    }
}