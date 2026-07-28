package com.jonbj.alembic.monitor.core.security

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

interface AesGcmCipher {
    fun encrypt(plaintext: String): ByteArray
    fun decrypt(ciphertext: ByteArray): String
}

class AndroidKeystoreAesGcmCipher(
    alias: String = "alembic_session_key"
) : AesGcmCipher {

    private val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    private val key: SecretKey = keyStore.getKey(alias, null) as? SecretKey ?: generateKey(alias)

    companion object {
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val GCM_TAG_LENGTH_BITS = 128
        private const val GCM_IV_LENGTH_BYTES = 12
    }

    override fun encrypt(plaintext: String): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val iv = cipher.iv
        val ciphertext = cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8))
        return encode(iv, ciphertext)
    }

    override fun decrypt(ciphertext: ByteArray): String {
        val (iv, encrypted) = decode(ciphertext)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(GCM_TAG_LENGTH_BITS, iv))
        return String(cipher.doFinal(encrypted), Charsets.UTF_8)
    }

    private fun generateKey(alias: String): SecretKey {
        val spec = KeyGenParameterSpec.Builder(
            alias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setRandomizedEncryptionRequired(true)
            .build()
        return KeyGenerator.getInstance("AES", "AndroidKeyStore").apply {
            init(spec)
        }.generateKey()
    }

    private fun encode(iv: ByteArray, ciphertext: ByteArray): ByteArray {
        val buffer = ByteBuffer.allocate(4 + iv.size + ciphertext.size)
            .order(ByteOrder.BIG_ENDIAN)
        buffer.putInt(iv.size)
        buffer.put(iv)
        buffer.put(ciphertext)
        return buffer.array()
    }

    private fun decode(data: ByteArray): Pair<ByteArray, ByteArray> {
        require(data.size >= Int.SIZE_BYTES + GCM_IV_LENGTH_BYTES + GCM_TAG_LENGTH_BITS / 8) {
            "Invalid encrypted payload"
        }
        val buffer = ByteBuffer.wrap(data).order(ByteOrder.BIG_ENDIAN)
        val ivLength = buffer.int
        require(ivLength == GCM_IV_LENGTH_BYTES && buffer.remaining() > ivLength) {
            "Invalid encrypted payload"
        }
        val iv = ByteArray(ivLength)
        buffer.get(iv)
        val ciphertext = ByteArray(buffer.remaining())
        buffer.get(ciphertext)
        return iv to ciphertext
    }
}
