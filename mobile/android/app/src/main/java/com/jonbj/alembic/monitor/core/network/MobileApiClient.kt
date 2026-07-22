package com.jonbj.alembic.monitor.core.network

import com.jonbj.alembic.monitor.BuildConfig
import com.jonbj.alembic.monitor.core.security.SessionVault
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

object MobileApiClient {

    private const val CONNECT_TIMEOUT_SECONDS = 10L
    private const val READ_TIMEOUT_SECONDS = 30L

    fun create(baseUrl: String, sessionVault: SessionVault, json: Json): MobileApi {
        val authInterceptor = AuthInterceptor(sessionVault)
        val client = OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .addInterceptor(authInterceptor)
            .apply {
                if (BuildConfig.DEBUG) {
                    addNetworkInterceptor(
                        HttpLoggingInterceptor().apply {
                            level = HttpLoggingInterceptor.Level.HEADERS
                        }
                    )
                }
            }
            .build()

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(json.asConverterFactory(okhttp3.MediaType.get("application/json")))
            .build()
            .create(MobileApi::class.java)
    }
}

class AuthInterceptor(private val sessionVault: SessionVault) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val original = chain.request()
        val session = sessionVault.getBlocking() ?: return chain.proceed(original)

        val request = original.newBuilder()
            .header("Authorization", "Bearer ${session.accessToken}")
            .header("Accept", "application/json")
            .method(original.method(), original.body())
            .build()
        return chain.proceed(request)
    }
}
