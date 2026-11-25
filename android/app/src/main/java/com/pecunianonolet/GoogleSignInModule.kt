package com.pecunianonolet

import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialException
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class GoogleSignInModule(private val context: ReactApplicationContext) :
  ReactContextBaseJavaModule(context) {

  private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

  override fun getName() = "GoogleSignIn"

  @ReactMethod
  fun signIn(serverClientId: String, nonce: String, promise: Promise) {
    val activity = context.currentActivity
    if (activity == null) {
      promise.reject("GOOGLE_SIGN_IN_NO_ACTIVITY", "No foreground activity is available for Google sign-in.")
      return
    }
    if (serverClientId.isBlank() || nonce.isBlank()) {
      promise.reject("GOOGLE_SIGN_IN_INVALID_ARGUMENT", "Google client ID and nonce are required.")
      return
    }

    val option = GetSignInWithGoogleOption.Builder(serverClientId)
      .setNonce(nonce)
      .build()
    val request = GetCredentialRequest.Builder()
      .addCredentialOption(option)
      .build()

    scope.launch {
      try {
        val result = CredentialManager.create(context).getCredential(activity, request)
        val credential = result.credential
        if (credential !is CustomCredential ||
          credential.type != GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
        ) {
          promise.reject("GOOGLE_SIGN_IN_UNEXPECTED_CREDENTIAL", "Google returned an unsupported credential.")
          return@launch
        }
        val idToken = GoogleIdTokenCredential.createFrom(credential.data).idToken
        promise.resolve(idToken)
      } catch (error: GoogleIdTokenParsingException) {
        promise.reject("GOOGLE_SIGN_IN_INVALID_TOKEN", error.message, error)
      } catch (error: GetCredentialException) {
        promise.reject("GOOGLE_SIGN_IN_CREDENTIAL_ERROR", "${error.type}: ${error.message}", error)
      } catch (error: Exception) {
        promise.reject("GOOGLE_SIGN_IN_FAILED", error.message, error)
      }
    }
  }
}
