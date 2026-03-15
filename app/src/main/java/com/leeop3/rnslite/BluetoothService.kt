package com.leeop3.rnslite
import android.annotation.SuppressLint
import android.bluetooth.*
import android.util.Log
import kotlinx.coroutines.*
import java.io.*
import java.util.*

class BluetoothService {
    private val SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    private var socket: BluetoothSocket? = null
    var inputStream: InputStream? = null
    var outputStream: OutputStream? = null

    @SuppressLint("MissingPermission")
    fun getPairedDevices(): List<Pair<String, String>> {
        val adapter = BluetoothAdapter.getDefaultAdapter() ?: return emptyList()
        return adapter.bondedDevices.map { it.name to it.address }
    }

    @SuppressLint("MissingPermission")
    suspend fun connect(address: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val adapter = BluetoothAdapter.getDefaultAdapter()
            val device = adapter.getRemoteDevice(address)
            
            // Close any existing socket
            try { socket?.close() } catch(e: Exception) {}
            
            socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
            adapter.cancelDiscovery()
            socket?.connect()
            
            inputStream = socket?.inputStream
            outputStream = socket?.outputStream
            Log.d("BT", "Connected successfully to $address")
            true
        } catch (e: Exception) {
            Log.e("BT", "Connect failed: ${e.message}")
            false
        }
    }

    fun read(maxBytes: Int): ByteArray {
        return try {
            val buf = ByteArray(maxBytes)
            val n = inputStream?.read(buf) ?: 0
            if (n > 0) buf.copyOf(n) else ByteArray(0)
        } catch (e: Exception) { ByteArray(0) }
    }

    fun write(data: ByteArray) {
        try { outputStream?.write(data) } catch (e: Exception) { Log.e("BT", "Write failed") }
    }
}