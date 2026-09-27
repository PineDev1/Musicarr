import SwiftUI

struct LoginView: View {
    @EnvironmentObject var session: SessionStore
    @State private var username = ""
    @State private var password = ""
    @State private var isLoading = false

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            ScrollView {
                VStack(spacing: 20) {
                    Spacer(minLength: 60)

                    VStack(spacing: 6) {
                        Image(systemName: "waveform")
                            .font(.system(size: 44))
                            .foregroundStyle(Theme.accent)
                        Text("Musicarr")
                            .font(.largeTitle.bold())
                            .foregroundStyle(Theme.text)
                        Text("Your library, streamed at original quality")
                            .font(.subheadline)
                            .foregroundStyle(Theme.muted)
                    }

                    VStack(alignment: .leading, spacing: 14) {
                        field(label: "Server address", text: $session.serverURLText, placeholder: "192.168.1.10:8787", keyboard: .URL)
                        field(label: "Username", text: $username, placeholder: "admin")
                        secureField(label: "Password", text: $password)

                        if let error = session.loginError {
                            Text(error)
                                .font(.footnote)
                                .foregroundStyle(Theme.danger)
                        }

                        Button {
                            isLoading = true
                            Task {
                                await session.login(username: username, password: password)
                                isLoading = false
                            }
                        } label: {
                            HStack {
                                Spacer()
                                if isLoading {
                                    ProgressView().tint(.black)
                                } else {
                                    Text("Sign in").bold()
                                }
                                Spacer()
                            }
                            .padding(.vertical, 14)
                        }
                        .background(Theme.accent)
                        .foregroundStyle(.black)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .disabled(isLoading || username.isEmpty || password.isEmpty || session.serverURLText.isEmpty)
                    }
                    .padding(20)
                    .background(Theme.backgroundElevated)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .padding(.horizontal, 20)

                    Spacer(minLength: 40)
                }
            }
        }
    }

    private func field(label: String, text: Binding<String>, placeholder: String, keyboard: UIKeyboardType = .default) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.caption).foregroundStyle(Theme.muted)
            TextField(placeholder, text: text)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(keyboard)
                .padding(12)
                .background(Theme.backgroundSoft)
                .foregroundStyle(Theme.text)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }

    private func secureField(label: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.caption).foregroundStyle(Theme.muted)
            SecureField("", text: text)
                .padding(12)
                .background(Theme.backgroundSoft)
                .foregroundStyle(Theme.text)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }
}
