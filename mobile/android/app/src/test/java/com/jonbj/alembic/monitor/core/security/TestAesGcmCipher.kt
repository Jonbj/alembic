package com.jonbj.alembic.monitor.core.security

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Software-only AES-GCM cipher for JVM unit tests. Never use in production;
 * it relies on a fixed test key that is not protected by the hardware keystore.
 */
class TestAesGcmCipher : AesGcmCipher {

    private val key = SecretKeySpec(TEST_KEY, "AES")
    private val random = SecureRandom()

    companion object {
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val GCM_TAG_LENGTH_BITS = 128
        private const val GCM_IV_LENGTH_BYTES = 12
        private val TEST_KEY = ByteArray(32).apply {
            for (i in indices) {
                this[i] = (i + 1).toByte()
            }
        }
    }

    override fun encrypt(plaintext: String): ByteArray {
        val iv = ByteArray(GCM_IV_LENGTH_BYTES).apply { random.nextBytes(this) }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(GCM_TAG_LENGTH_BITS, iv))
        val ciphertext = cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8))
        return encode(iv, ciphertext)
    }

    override fun decrypt(ciphertext: ByteArray): String {
        val (iv, encrypted) = decode(ciphertext)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(GCM_TAG_LENGTH_BITS, iv))
        return String(cipher.doFinal(encrypted), Charsets.UTF_8)
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
        val buffer = ByteBuffer.wrap(data).order(ByteOrder.BIG_ENDIAN)
        val ivLength = buffer.int
        val iv = ByteArray(ivLength)
        buffer.get(iv)
        val encrypted = ByteArray(buffer.remaining())
        buffer.get(encrypted)
        return iv to encrypted
    }
}
