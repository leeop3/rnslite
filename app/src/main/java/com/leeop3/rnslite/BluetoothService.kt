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
        val adapter = BluetoothAdapter.getDefaultAdapter()
        val device = adapter.getRemoteDevice(address)
        
        // 1. Try Secure Connection
        Log.d("BT", "Attempting Secure connection to $address")
        if (connectAttempt(device, true)) return@withContext true
        
        // 2. Fallback: Try Insecure Connection (Common fix for RNode/ESP32)
        Log.w("BT", "Secure failed, attempting Insecure connection...")
        delay(500) // Brief rest for the BT stack
        if (connectAttempt(device, false)) return@withContext true
        
        false
    }

    @SuppressLint("MissingPermission")
    private fun connectAttempt(device: BluetoothDevice, secure: Boolean): Boolean {
        return try {
            val adapter = BluetoothAdapter.getDefaultAdapter()
            if (adapter.isDiscovering) adapter.cancelDiscovery()
            
            socket?.close()
            socket = if (secure) {
                device.createRfcommSocketToServiceRecord(SPP_UUID)
            } else {
                device.createInsecureRfcommSocketToServiceRecord(SPP_UUID)
            }
            
            socket?.connect()
            inputStream = socket?.inputStream
            outputStream = socket?.outputStream
            Log.i("BT", "Connected successfully (${if (secure) "Secure" else "Insecure"})")
            true
        } catch (e: Exception) {
            Log.e("BT", "Connection attempt failed: ${e.message}")
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
        try { outputStream?.write(data) } catch (e: Exception) { }
    }
}