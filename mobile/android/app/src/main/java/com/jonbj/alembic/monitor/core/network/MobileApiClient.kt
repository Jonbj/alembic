package com.jonbj.alembic.monitor.core.network

import com.jonbj.alembic.monitor.BuildConfig
import com.jonbj.alembic.monitor.core.security.SessionVault
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit
import java.util.concurrent.ConcurrentHashMap

object MobileApiClient {

    private const val CONNECT_TIMEOUT_SECONDS = 10L
    private const val READ_TIMEOUT_SECONDS = 30L

    fun create(baseUrl: String, sessionVault: SessionVault, json: Json): MobileApi {
        val client = createHttpClient(
            sessionVault = sessionVault,
            enableDebugLogging = BuildConfig.DEBUG
        )

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(MobileApi::class.java)
    }

    internal fun createHttpClient(
        sessionVault: SessionVault,
        enableDebugLogging: Boolean
    ): OkHttpClient {
        return OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .addInterceptor(AuthInterceptor(sessionVault))
            .apply {
                if (enableDebugLogging) {
                    addNetworkInterceptor(
                        HttpLoggingInterceptor().apply {
                            redactHeader("Authorization")
                            redactHeader("Cookie")
                            redactHeader("Set-Cookie")
                            level = HttpLoggingInterceptor.Level.HEADERS
                        }
                    )
                }
            }
            .build()
    }
}

interface MobileApiProvider {
    fun forBaseUrl(baseUrl: String): MobileApi
    fun current(): MobileApi
}

class SessionMobileApiProvider(
    private val defaultBaseUrl: String,
    private val sessionVault: SessionVault,
    private val json: Json
) : MobileApiProvider {
    private val clients = ConcurrentHashMap<String, MobileApi>()

    override fun forBaseUrl(baseUrl: String): MobileApi =
        clients.getOrPut(baseUrl) { MobileApiClient.create(baseUrl, sessionVault, json) }

    override fun current(): MobileApi {
        val baseUrl = sessionVault.getBlocking()?.baseUrl ?: defaultBaseUrl
        return forBaseUrl(baseUrl)
    }
}

class FixedMobileApiProvider(
    private val api: MobileApi
) : MobileApiProvider {
    override fun forBaseUrl(baseUrl: String): MobileApi = api
    override fun current(): MobileApi = api
}

class AuthInterceptor(private val sessionVault: SessionVault) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val original = chain.request()
        val session = sessionVault.getBlocking() ?: return chain.proceed(original)

        val request = original.newBuilder()
            .header("Authorization", "Bearer ${session.accessToken}")
            .header("Accept", "application/json")
            .method(original.method, original.body)
            .build()
        return chain.proceed(request)
    }
}
