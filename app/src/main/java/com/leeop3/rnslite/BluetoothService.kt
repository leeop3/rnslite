package com.leeop3.rnslite
import android.annotation.SuppressLint
import android.bluetooth.*
import kotlinx.coroutines.*
import java.io.*
import java.util.*

class BluetoothService {
    private val SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    private var socket: BluetoothSocket? = null
    private var inputStream: InputStream? = null
    private var outputStream: OutputStream? = null

    @SuppressLint("MissingPermission")
    fun getPairedDevices(): List<Pair<String, String>> {
        val adapter = BluetoothAdapter.getDefaultAdapter() ?: return emptyList()
        return adapter.bondedDevices.map { it.name to it.address }
    }

    @SuppressLint("MissingPermission")
    suspend fun connect(address: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val device = BluetoothAdapter.getDefaultAdapter().getRemoteDevice(address)
            socket?.close()
            socket = device.createInsecureRfcommSocketToServiceRecord(SPP_UUID)
            socket?.connect()
            inputStream = socket?.inputStream
            outputStream = socket?.outputStream
            true
        } catch (e: Exception) { false }
    }

    fun read(maxBytes: Int): ByteArray {
        return try {
            val available = inputStream?.available() ?: 0
            if (available > 0) {
                val buf = ByteArray(if (available > maxBytes) maxBytes else available)
                val n = inputStream?.read(buf) ?: 0
                if (n > 0) buf.copyOf(n) else ByteArray(0)
            } else ByteArray(0)
        } catch (e: Exception) { ByteArray(0) }
    }

    fun write(data: ByteArray) {
        try {
            outputStream?.write(data)
            outputStream?.flush()
        } catch (e: Exception) { }
    }

    fun disconnect() {
        try { socket?.close() } catch (e: Exception) {}
    }
}